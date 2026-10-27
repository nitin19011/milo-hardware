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
from dataset_tools import PROFILE, FINGERS, FEATURES, flatten, quality, make_calibration, calibrate, release_candidate, write_clip, export_dataset
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
            with (self.folder/'raw_stream.jsonl').open('w',encoding='utf-8') as sf, (self.folder/'events.jsonl').open('w',encoding='utf-8') as ef:
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
        time.sleep(.03)
    if ack is None:raise RuntimeError('Glove did not acknowledge capture; no gesture should be performed.')
    ack_delay=time.monotonic()-sent
    timing={'ack':ack,'ack_roundtrip_s':round(ack_delay,3),'cue_events':[]}
    latest,_,_,_=r.snapshot();elapsed=max(0,(latest['timestamp_us']-ack['start_us'])/1000)
    started=time.monotonic()-elapsed/1000
    go=False;return_cued=False
    print('Recording lead-in...' if lead else 'HOLD STILL - recording',flush=True)
    end=started+duration/1000
    while time.monotonic()<end:
        r.check();now=time.monotonic();ms=(now-started)*1000
        if not go and ms>=lead:
            beep();print('GO' if lead else 'HOLD',flush=True);go=True
            latest,_,_,_=r.snapshot()
            timing['cue_events'].append({'type':'go','host_utc':utc_now(),'estimated_elapsed_ms':round(ms),'latest_sensor_elapsed_ms':int((latest['timestamp_us']-ack['start_us'])/1000) if latest and latest['boot_id']==boot else None})
        if action_end is not None and not return_cued and ms>=action_end:
            print('Finish naturally / relax.',flush=True);beep();return_cued=True
        time.sleep(.03)
    beep();print('STOP',flush=True)
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

def ask_review(throw):
    prompt='Did you perform ONE intended gesture correctly?'
    if throw:prompt+=' Include the loose grip, swing AND finger release.'
    print(prompt)
    value=input('[Enter=accept, r=redo, s=skip, q=finish] ').strip().lower()
    return value if value in ['r','s','q'] else 'accept'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='172.20.10.2');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--participant',default='Nitin');p.add_argument('--reps',type=int,default=3)
    p.add_argument('--role',choices=['unassigned','train','validation','test'],default='unassigned')
    p.add_argument('--classes',nargs='+',help='Collect only selected class IDs, e.g. throw_overhand throw_underhand background')
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('gestures.json'))
    p.add_argument('--output',type=Path,default=Path(__file__).with_name('datasets'))
    p.add_argument('--speak',action='store_true');p.add_argument('--seed',type=int,default=None)
    a=p.parse_args()
    if not 1<=a.reps<=100:raise SystemExit('Use 1..100 repetitions per class.')
    import paho.mqtt.client as mqtt
    cfg=json.loads(a.config.read_text(encoding='utf-8-sig'))
    if cfg['sample_hz']!=50 or type(cfg['clip_ms']) is not int or not 1000<=cfg['clip_ms']<=30000 or cfg['clip_ms']%20:
        raise SystemExit('Use 50 Hz clips lasting 1000..30000 ms in multiples of 20 ms.')
    for c in cfg['classes']:
        for variant in c.get('variants',[c]):gesture_timing(cfg,c,variant)
    ids=[c['id'] for c in cfg['classes']]
    if len(set(ids))!=len(ids) or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',v) for v in ids):
        raise SystemExit('Class IDs must be unique lowercase names using letters, digits and underscores.')
    selected=[c for c in cfg['classes'] if not a.classes or c['id'] in a.classes]
    if not selected or (a.classes and set(a.classes)-{c['id'] for c in selected}):raise SystemExit('Unknown/empty class selection.')
    token=uuid.uuid4().hex[:16];session_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+token
    seed=a.seed if a.seed is not None else int(token[:8],16)
    folder=a.output/session_id;folder.mkdir(parents=True)
    manifest={'format_version':1,'participant':a.participant,'session_id':session_id,'session_token':token,'split_role':a.role,
        'class_order':[c['id'] for c in cfg['classes']],'class_definitions':cfg,'definition_sha256':hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),
        'hardware_profile':PROFILE,'sample_hz':50,'clip_ms':cfg['clip_ms'],'random_seed':seed,'repetitions_requested':a.reps,'class_selection':[c['id'] for c in selected],
        'capture_notes':'Personal model; empty-hand simulated ball throws. Cue timing is guidance, not exact annotated onset/release.',
        'complete':False,'quality_rejections':0,'accepted_clips':0}
    (folder/'session.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    r=Recorder(folder,token);client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='gesture-capture-'+token)
    client.on_connect=r.on_connect;client.on_disconnect=r.on_disconnect;client.on_message=r.on_message
    trial=0;calibration=None;finished_early=False;error=None
    print('Milo personal gesture collection. Battery-powered glove; updated MAIN MBF_v1 firmware required.')
    print('Wear the glove normally. One gesture per recording. Save failures rather than hiding bad readings.')
    print('Session:',folder)
    try:
        client.connect_async(a.host,a.port,keepalive=5);client.loop_start();r.live(60)
        clips={}
        poses=[('open','Support the hand palm down, fingers comfortably straight. Hold still.'),
               ('fist','Make a comfortable full fist including the thumb, with wrist still. This is calibration only.'),
               ('ball_grip','Hold an imaginary ball naturally. Fingers partly curved, much looser than a fist. Wrist still.')]
        for name,instruction in poses:
            while True:
                announce('Calibration '+name+': '+instruction,a.speak);input('Press Enter when holding the pose... ')
                trial+=1;rows,q,timing=capture(client,r,trial,4000)
                metadata={'kind':'calibration','clip_id':f'{token}_{trial:04d}','trial':trial,'pose':name,'duration_ms':4000,'quality':q,'timing':timing,'accepted':q['usable']}
                write_clip(folder,metadata['clip_id'],rows,metadata)
                if q['usable']:clips[name]=rows;break
                print('Calibration rejected:',', '.join(q['errors']))
                if input('Enter=retry, q=finish: ').strip().lower()=='q':raise KeyboardInterrupt
        calibration=make_calibration(clips)
        (folder/'calibration.json').write_text(json.dumps(calibration,indent=2),encoding='utf-8')
        print('Session calibration saved. Ball grip can be below the old BENT threshold; continuous values are recorded.')
        rng=random.Random(seed);schedule=[]
        for rep in range(a.reps):
            order=selected.copy();rng.shuffle(order)
            for c in order:schedule.append((rep,c))
        accepted_index=0;explained=set()
        for rep,c in schedule:
            variant=c.get('variants',[c])[rep%len(c.get('variants',[c]))]
            speed=['normal','slightly slower','slightly faster'][rep%3]
            instruction=variant.get('instruction',c.get('instruction',''))
            lead,action_end=gesture_timing(cfg,c,variant)
            key=(c['id'],variant.get('id',c['id']))
            announce(f"{c['id']}, repetition {rep+1}/{a.reps}."+(' '+instruction if key not in explained else ''),a.speak)
            explained.add(key)
            print(f"Recording: {lead/1000:g}s prepare, {(action_end-lead)/1000:g}s gesture, {(cfg['clip_ms']-action_end)/1000:g}s finish.")
            print('Suggested speed:',speed,'— vary naturally, preserve the same gesture definition.')
            while True:
                input('Press Enter to start; prepare during the recorded lead-in, move at GO... ')
                trial+=1;rows,q,timing=capture(client,r,trial,cfg['clip_ms'],lead,action_end)
                candidate=release_candidate(rows,calibration,lead,action_end) if rows and c.get('throw') else None
                if rows:
                    normalised=calibrate([[x[k] for k in FEATURES] for x in rows],calibration)
                    if np.any(normalised[:,6:9]>1.6) or np.any(normalised[:,6:9]<-.5):q['warnings'].append('flex_outside_session_calibration; inspect waveform before training')
                metadata={'kind':'gesture','clip_id':f'{token}_{trial:04d}','trial':trial,'class_id':c['id'],'variant':variant.get('id',c['id']),
                    'repetition':rep+1,'speed_prompt':speed,'duration_ms':cfg['clip_ms'],'lead_in_ms':lead,'action_end_ms':action_end,'quality':q,'timing':timing,'release_candidate':candidate,
                    'annotations':{'action_onset_ms':None,'release_ms':None,'action_end_ms':None,'source':'unannotated'},
                    'human_confirmed_release':False,'signal_reviewed':False,'accepted':False}
                print('Quality:', 'usable' if q['usable'] else 'QUARANTINED',q['errors'],q['warnings'])
                if not q['usable']:
                    manifest['quality_rejections']+=1
                    choice=input('Faulty clip saved; Enter=retry, s=skip, q=finish: ').strip().lower()
                    choice='r' if choice not in ['s','q'] else choice
                else:
                    choice=ask_review(c.get('throw',False))
                    metadata['accepted']=choice=='accept'
                    metadata['human_confirmed_release']=bool(c.get('throw') and choice=='accept')
                write_clip(folder,metadata['clip_id'],rows,metadata)
                r.event('clip_saved',metadata=metadata)
                if metadata['accepted']:accepted_index+=1
                if choice=='q':finished_early=True;break
                if choice!='r':break
            if finished_early:break
        manifest['accepted_clips']=accepted_index;manifest['complete']=not finished_early
    except (KeyboardInterrupt,EOFError):error='Stopped by user; partial session retained.'
    except Exception as e:error=str(e);print('Collection stopped:',error)
    finally:
        try:
            if client.is_connected():client.publish(CONTROL,'STOP '+token,qos=0,retain=False).wait_for_publish(timeout=2)
        except Exception:pass
        client.disconnect();client.loop_stop();r.close()
        manifest['error']=error or r.error;manifest['finished_utc']=utc_now()
        if manifest['error']:manifest['complete']=False
        (folder/'session.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if calibration:
            details=export_dataset([folder],folder/'export')
            manifest['training_export_clips']=details['accepted_clips']
            (folder/'session.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            print('Accepted training clips:',details['accepted_clips'])
            from review_session import build_review
            build_review(folder)
        archive=folder.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for f in folder.rglob('*'):
                if f.is_file():z.write(f,f.relative_to(folder))
        print('Send this session ZIP for review:',archive)
    return 0 if manifest['complete'] else 1

if __name__=='__main__':raise SystemExit(main())
