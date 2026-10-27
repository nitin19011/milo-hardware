"""Guided personal gesture capture, with ESP-stamped trials and quality-gated export."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import queue
import random
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime
import numpy as np
from dataset_tools import PROFILE, FINGERS, FEATURES, flatten, quality,  calibrate, release_candidate, write_clip, export_dataset
from capture_helpers import announce, beep, utc_now

DATA='sensor/glove/gesture'; CONTROL='collection/glove/control'; ACK='collection/glove/ack'

def gesture_timing(cfg,gesture,variant):
    lead=variant.get('lead_in_ms',gesture.get('lead_in_ms',cfg['lead_in_ms']))
    end=variant.get('action_end_ms',gesture.get('action_end_ms',cfg['action_end_ms']))
    if not all(type(v) is int for v in [lead,end]) or not 0<lead<end<cfg['clip_ms']:
        raise ValueError('Gesture cue times must fit inside the recording.')
    return lead,end

class Recorder:
    def __init__(self,folder,token):
        self.folder=folder;self.token=token;self.lock=threading.Lock();self.last=None;self.received=0
        self.ack=None;self.connected=False;self.error=None;self.config_error=None
        self.records=queue.Queue(maxsize=20000);self.done=threading.Event();self.dropped=0
        self.buckets=collections.defaultdict(list);self.closed=set()
        self.thread=threading.Thread(target=self.writer,daemon=True);self.thread.start()
    def emit(self,item):
        try:self.records.put_nowait(item)
        except queue.Full:self.dropped+=1
    def event(self,kind,**data):self.emit({'kind':kind,'utc':utc_now(),**data})
    def check(self):
        cancel=getattr(self,'cancel_check',None)
        if cancel:cancel()
        if self.config_error:raise RuntimeError(self.config_error)
        if self.error:raise RuntimeError(self.error)
        if self.dropped:raise RuntimeError('Laptop capture queue overflow; partial data preserved.')
    def snapshot(self):
        with self.lock:return self.last,self.received,self.connected,self.ack
    def live(self,seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            self.check();s,received,connected,_=self.snapshot()
            if s and connected and time.monotonic()-received<.5:return s
            time.sleep(.05)
        raise RuntimeError('No fresh main-mode data. Check the new MBF_v1 upload, battery, Wi-Fi and broker.')
    def on_connect(self,c,u,flags,reason,p):
        if reason.is_failure:self.event('broker_connect_failed',reason=str(reason));return
        with self.lock:self.connected=True
        c.subscribe([(DATA,0),(ACK,1)]);self.event('broker_connected')
    def on_disconnect(self,c,u,flags,reason,p):
        with self.lock:self.connected=False
        self.event('broker_disconnected',reason=str(reason))
    def on_message(self,c,u,msg):
        try:
            if len(msg.payload)>2048:raise ValueError('Oversized message')
            data=json.loads(msg.payload)
            if msg.retain:return
            if msg.topic==ACK:
                if data.get('session')==self.token:
                    with self.lock:self.ack=data
                    self.event('ack',data=data)
                return
            try:row=flatten(data)
            except ValueError as e:
                self.config_error=str(e);return
            self.emit({'kind':'sample','received_utc':utc_now(),'data':data})
            capture=data['collection']
            with self.lock:
                previous=self.last;self.last=row;self.received=time.monotonic()
                if capture['session']==self.token and capture['trial'] and capture['trial'] not in self.closed:
                    self.buckets[capture['trial']].append(row)
            if previous and row['boot_id']!=previous['boot_id']:
                self.event('boot_changed',before=previous['boot_id'],after=row['boot_id'])
        except (ValueError,KeyError,TypeError) as e:self.event('invalid_message',error=str(e))
    def writer(self):
        try:
            with (self.folder/'raw_stream.jsonl').open('a',encoding='utf-8') as sf, (self.folder/'events.jsonl').open('a',encoding='utf-8') as ef:
                while not self.done.is_set() or not self.records.empty():
                    try:item=self.records.get(timeout=.2)
                    except queue.Empty:continue
                    f=sf if item['kind']=='sample' else ef
                    f.write(json.dumps(item)+'\n');f.flush()
        except Exception as e:self.error='Saving capture failed: '+str(e)
    def close(self):
        self.done.set();self.thread.join(15)
        if self.thread.is_alive():self.error='Capture writer did not close.'

def capture(client,r,trial,duration,lead=0,action_end=None):
    before=r.live();boot=before['boot_id']
    with r.lock:r.ack=None
    sent=time.monotonic();next_send=0;deadline=sent+6
    command=f'GO {r.token} {trial} {duration}'
    ack=None
    while time.monotonic()<deadline:
        r.check();latest,_,connected,a=r.snapshot()
        if connected and time.monotonic()>=next_send:
            client.publish(CONTROL,command,qos=0,retain=False);next_send=time.monotonic()+.8
        if a and a.get('trial')==trial and a.get('boot')==boot:
            if not a.get('accepted'):raise RuntimeError('Another collection trial is active. Wait before retrying.')
            ack=a;break
        time.sleep(.01)
    if ack is None:raise RuntimeError('Glove did not acknowledge capture; no gesture should be performed.')
    ack_delay=time.monotonic()-sent
    timing={'ack':ack,'ack_roundtrip_s':round(ack_delay,3),'cue_events':[]}
    latest,_,_,_=r.snapshot();elapsed=max(0,(latest['timestamp_us']-ack['start_us'])/1000)
    started=time.monotonic()-elapsed/1000
    go=False;return_cued=False
    feedback=getattr(r,'feedback',None)
    if feedback:feedback('prepare' if lead else 'hold',duration_ms=duration,lead_ms=lead)
    else:print('Get ready...' if lead else 'Hold still...',flush=True)
    progress_at=0
    end=started+duration/1000
    while time.monotonic()<end:
        r.check();now=time.monotonic();ms=(now-started)*1000
        if feedback and now>=progress_at:
            feedback('recording_progress',elapsed_ms=min(duration,round(ms)),duration_ms=duration);progress_at=now+.05
        if not go and ms>=lead:
            if feedback:feedback('go' if lead else 'hold',duration_ms=duration,lead_ms=lead)
            else:print('GO - perform the gesture' if lead else 'Hold still...',flush=True)
            beep();go=True
            latest,_,_,_=r.snapshot()
            timing['cue_events'].append({'type':'go','host_utc':utc_now(),'estimated_elapsed_ms':round(ms),'latest_sensor_elapsed_ms':int((latest['timestamp_us']-ack['start_us'])/1000) if latest and latest['boot_id']==boot else None})
        if action_end is not None and not return_cued and ms>=action_end:
            print('Finish naturally / relax.',flush=True);beep();return_cued=True
        time.sleep(.01)
    beep()
    if feedback:feedback('stop',duration_ms=duration)
    else:print('Recording complete.',flush=True)
    # Wait for buffered samples rather than relabelling them by receive time.
    delivery_deadline=time.monotonic()+3
    while time.monotonic()<delivery_deadline:
        r.check()
        with r.lock:rows=list(r.buckets.get(trial,[]))
        if len(rows)>=duration//20:break
        time.sleep(.05)
    with r.lock:
        rows=list(r.buckets.pop(trial,[]));r.closed.add(trial)
    q=quality(rows,duration)
    if ack_delay>.5:q['warnings'].append('command_ack_delayed; cue timing needs review')
    if lead and not go:
        q['usable']=False;q['errors'].append('missing_go_cue')
    current,_,_,_=r.snapshot()
    if current and current['boot_id']!=boot:
        q['usable']=False;q['errors'].append('board_restart_during_capture')
    return rows,q,timing

