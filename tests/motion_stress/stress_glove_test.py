"""Wireless motion stress test. Compatible with the already-uploaded diagnostic sketch."""
import argparse
import csv
import json
import math
from pathlib import Path
import queue
import threading
import time
import uuid
import zipfile
from datetime import datetime
from guided_glove_test import DATA, STATUS, ACK, CONTROL, FIELDS, FLEX, AXES, stats, utc_now, announce, beep

PLAN = [
    ('baseline_still',12,'Rest your forearm on a table. Palm down, fingers straight, completely still.'),
    ('moderate_wrist',20,'Make comfortable wrist circles, then tilt the hand up and down. Keep fingers mostly straight.'),
    ('still_after_wrist',8,'Return to the supported palm-down position. Straighten fingers and keep still.'),
    ('quick_palm_flips',20,'Turn palm up and down quickly and repeatedly. Use a comfortable range; keep fingers mostly straight.'),
    ('still_after_flips',8,'Rest palm down again. Straight fingers, completely still.'),
    ('arm_sweeps',20,'Swing your arm briskly forward and back, then left and right. Keep clear of surrounding objects.'),
    ('still_after_sweeps',8,'Rest palm down again. Straight fingers, completely still.'),
    ('circles_and_figure_eights',20,'Make broad arm circles and figure-eight sweeps, changing direction several times.'),
    ('fast_direction_changes',20,'Make short brisk hand sweeps and change direction. Keep within a comfortable range; avoid impacts.'),
    ('moving_finger_cycles',20,'While gently swinging the arm, alternate an open hand and a comfortable fist every two seconds.'),
    ('final_still',12,'Rest in the original palm-down position, straighten every finger, and keep completely still.'),
]

CSV_FIELDS = FIELDS + ['host_trial','host_label','label_source']

class Recorder:
    def __init__(self, folder, session):
        self.folder=folder;self.session=session;self.lock=threading.Lock()
        self.inbox=queue.Queue(maxsize=20000);self.finished=threading.Event()
        self.last=None;self.last_receive=0;self.connected=False;self.ack=None
        self.host_trial=0;self.host_label='preparation';self.error=None;self.local_dropped=0
        self.samples=[];self.events=[];self.trials=[]
        self.worker=threading.Thread(target=self.write_records,daemon=True);self.worker.start()
    def enqueue(self, item):
        try:self.inbox.put_nowait(item)
        except queue.Full:self.local_dropped+=1
    def event(self, kind, **data):
        self.enqueue({'kind':kind,'utc':utc_now(),'monotonic':time.monotonic(),**data})
    def set_phase(self, trial, label):
        with self.lock:self.host_trial=trial;self.host_label=label
        self.event('host_phase',trial=trial,label=label)
    def snapshot(self):
        with self.lock:return self.last,self.last_receive,self.connected,self.ack
    def fatal_check(self):
        # A sensor/radio fault is evidence; only a laptop recording failure aborts.
        if self.error:raise RuntimeError('Laptop recording failed: '+self.error)
        if self.local_dropped:raise RuntimeError('Laptop queue overflowed; partial data saved.')
    def on_connect(self,c,u,flags,reason,properties):
        if reason.is_failure:self.event('broker_connect_failed',reason=str(reason));return
        with self.lock:self.connected=True
        c.subscribe([(DATA,0),(ACK,1),(STATUS,1)]);self.event('broker_connected')
    def on_disconnect(self,c,u,flags,reason,properties):
        with self.lock:self.connected=False
        self.event('broker_disconnected',reason=str(reason))
    def on_message(self,c,u,msg):
        try:
            if len(msg.payload)>2048:raise ValueError('Oversized message')
            data=json.loads(msg.payload)
            if not isinstance(data,dict):raise ValueError('Expected object')
            if msg.topic==DATA:
                if msg.retain:return
                required=['version','boot','session','trial','seq','timestamp_us','elapsed_ms','imu_ok',*FLEX,'queue_dropped','imu_errors','rssi_dbm']
                if data.get('version')!=1 or any(k not in data for k in required):raise ValueError('Unexpected diagnostic schema')
                if any(type(data[k]) is not int or not 0<=data[k]<=4095 for k in FLEX):raise ValueError('Invalid ADC')
                if data['imu_ok'] and any(not isinstance(data.get(k),(int,float)) or not math.isfinite(data[k]) for k in AXES):raise ValueError('Invalid IMU value')
                now=time.monotonic()
                with self.lock:
                    previous=self.last;previous_time=self.last_receive
                    host_trial=self.host_trial;host_label=self.host_label
                    self.last=data;self.last_receive=now
                if previous:
                    if data['boot']!=previous['boot']:
                        self.event('boot_changed',before=previous['boot'],after=data['boot'],host_trial=host_trial)
                    if now-previous_time>1:
                        self.event('receive_gap_recovered',gap_s=round(now-previous_time,3),host_trial=host_trial)
                self.enqueue({'kind':'sample','received_utc':utc_now(),'receive_monotonic':now,
                              'host_trial':host_trial,'host_label':host_label,'data':data})
            elif msg.topic==ACK:
                if not msg.retain and data.get('session')==self.session:
                    with self.lock:self.ack=data
                    self.event('ack',data=data)
            else:
                with self.lock:current=self.last['boot'] if self.last else None
                # Preserve old wills, but don't attribute another boot's OFFLINE to this run.
                self.event('glove_status',retained=msg.retain,active_boot=current,
                           matches_active_boot=(current is not None and data.get('boot')==current),data=data)
        except (ValueError,TypeError,KeyError) as e:self.event('invalid_message',error=str(e))
    def write_records(self):
        try:
            with (self.folder/'samples.csv').open('w',newline='',encoding='utf-8') as cf, \
                 (self.folder/'raw_samples.jsonl').open('w',encoding='utf-8') as rf, \
                 (self.folder/'events.jsonl').open('w',encoding='utf-8') as ef:
                writer=csv.DictWriter(cf,fieldnames=CSV_FIELDS);writer.writeheader()
                while not self.finished.is_set() or not self.inbox.empty():
                    try:item=self.inbox.get(timeout=.2)
                    except queue.Empty:continue
                    if item['kind']=='sample':
                        row=item['data']
                        phase=next((t for t in self.trials if t['trial']==row['trial']),None)
                        esp_labelled=row.get('session')==self.session and bool(row['trial']) and phase is not None
                        label=phase['label'] if esp_labelled else 'idle_or_unlabelled'
                        writer.writerow({**{k:row.get(k) for k in FIELDS},'received_utc':item['received_utc'],
                            'trial_label':label,'host_trial':item['host_trial'],'host_label':item['host_label'],
                            'label_source':'esp_acquisition' if esp_labelled else 'host_context_only'})
                        rf.write(json.dumps(item)+'\n');self.samples.append(item)
                        cf.flush();rf.flush()
                    else:ef.write(json.dumps(item)+'\n');self.events.append(item);ef.flush()
        except Exception as e:self.error=str(e)
    def close(self):
        self.finished.set();self.worker.join(15)
        if self.worker.is_alive():self.error='Recording worker did not finish.'

def continuity(records):
    result={'received_samples':len(records),'boots':[], 'missing_sequences':0,
            'duplicate_or_out_of_order_sequences':0,'new_queue_drops':0,'imu_invalid_samples':0,
            'gyro_clipped_samples':0,'accel_clipped_samples':0,
            'receive_gaps_over_1s':[],'sample_gaps_over_40ms':[],'flex_near_rail':{k:0 for k in FLEX}}
    last={};intervals=[];rssi=[];spans={k:[] for k in FLEX}
    previous_receive=None
    for item in records:
        row=item['data'];boot=row['boot'];received=item['receive_monotonic']
        if boot not in result['boots']:result['boots'].append(boot)
        if previous_receive is not None and received-previous_receive>1:
            result['receive_gaps_over_1s'].append({'gap_s':round(received-previous_receive,3),'seq':row['seq'],'host_trial':item['host_trial']})
        previous_receive=received
        previous=last.get(boot)
        if previous:
            step=row['seq']-previous['seq']
            result['missing_sequences']+=max(0,step-1)
            result['duplicate_or_out_of_order_sequences']+=int(step<=0)
            result['new_queue_drops']+=max(0,row['queue_dropped']-previous['queue_dropped'])
            dt=(row['timestamp_us']-previous['timestamp_us'])/1000
            intervals.append(dt)
            if dt>40:result['sample_gaps_over_40ms'].append({'gap_ms':round(dt,3),'seq':row['seq']})
        last[boot]=row
        result['imu_invalid_samples']+=int(not row['imu_ok'])
        result['gyro_clipped_samples']+=int(row['imu_ok'] and any(abs(row.get('raw_'+k,0))>=32700 for k in ('gx','gy','gz')))
        result['accel_clipped_samples']+=int(row['imu_ok'] and any(abs(row.get('raw_'+k,0))>=32700 for k in ('ax','ay','az')))
        for k in FLEX:
            result['flex_near_rail'][k]+=int(row[k]<=20 or row[k]>=4075)
            spans[k].append(row[k])
        rssi.append(row['rssi_dbm'])
    result['sampling_intervals_ms']=stats(intervals);result['rssi_dbm']=stats(rssi)
    result['flex']= {k:stats(v) for k,v in spans.items()}
    return result

def make_summary(r):
    whole=continuity(r.samples)
    _,last_receive,_,_=r.snapshot()
    whole['data_age_at_end_s']=round(max(0,time.monotonic()-last_receive),3) if last_receive else None
    whole['link_warnings']=[e for e in r.events if e['kind']=='live_link_warning']
    whole['observed_boot_changes']=sum(e['kind']=='boot_changed' for e in r.events)
    whole['broker_disconnect_events']=[e for e in r.events if e['kind']=='broker_disconnected' and e.get('reason')!='Normal disconnection']
    whole['active_boot_offline_statuses']=[e for e in r.events if e['kind']=='glove_status' and e.get('matches_active_boot') and e.get('data',{}).get('state')=='OFFLINE']
    whole['ignored_other_boot_offline_statuses']=sum(e['kind']=='glove_status' and not e.get('matches_active_boot') and e.get('data',{}).get('state')=='OFFLINE' for e in r.events)
    phases=[]
    for trial in r.trials:
        # Use acquisition tags for sensor statistics; keep host-window context separately.
        selected=[i for i in r.samples if i['data'].get('session')==r.session and i['data']['trial']==trial['trial']]
        stable=[i for i in selected if i['data']['elapsed_ms']>=1000]
        valid=[i['data'] for i in stable if i['data']['imu_ok']]
        phase={**trial,**continuity(selected),'expected_approx_samples':trial['duration_s']*50,
               'axes':{k:stats(v[k] for v in valid) for k in AXES},
               'static_flex':{k:stats(i['data'][k] for i in stable) for k in FLEX},
               'host_context_unlabelled_samples':sum(i['host_trial']==trial['trial'] and (i['data']['session']!=r.session or not i['data']['trial']) for i in r.samples)}
        phase['warnings']=[]
        if len(selected)<trial['duration_s']*50*.9:phase['warnings'].append('Under 90% of expected labelled samples; inspect resets and link gaps.')
        if phase['imu_invalid_samples']:phase['warnings'].append('Checked IMU I2C failures.')
        if phase['gyro_clipped_samples']:phase['warnings'].append('Gyroscope clipped at the existing +/-500 deg/s range; not by itself a disconnect.')
        if phase['accel_clipped_samples']:phase['warnings'].append('Accelerometer clipped at the existing +/-4 g range; not by itself a disconnect.')
        phases.append(phase)
    labels={p['label']:p for p in phases}
    comparison={}
    for k in FLEX:
        a=labels.get('baseline_still',{}).get('static_flex',{}).get(k)
        b=labels.get('final_still',{}).get('static_flex',{}).get(k)
        if a and b:comparison[k]={'before_median':a['median'],'after_median':b['median'],'change':b['median']-a['median']}
    return {'note':'Connectivity stress evidence. Clipping and receive delays are reported separately from electrical faults.',
            'whole_recording':whole,'trials':phases,'baseline_to_final':comparison,
            'interpretation':'No missing sequences can still coexist with delayed delivery. An MCU restart identifies a new boot but does not establish its electrical cause.'}

def wait_live(r,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        r.fatal_check();sample,last,connected,_=r.snapshot()
        if connected and sample and time.monotonic()-last<.5:return sample
        time.sleep(.1)
    return None

def run_trial(c,r,trial,speak):
    r.set_phase(0,'preparation')
    print(f"\n[{trial['trial']}/{len(r.trials)}] {trial['label']} - {trial['duration_s']} seconds")
    announce(trial['instruction'],speak)
    input('Press ENTER when ready... ')
    print('Waiting for live glove data...')
    sample=wait_live(r)
    if sample is None:
        r.event('trial_skipped_no_link',trial=trial['trial']);print('No live link. Trial skipped; recording continues.');return False
    for n in (3,2,1):print(n,flush=True);time.sleep(1)
    r.set_phase(trial['trial'],trial['label'])
    with r.lock:r.ack=None
    command=f"GO {r.session} {trial['trial']} {trial['duration_s']*1000}"
    deadline=time.monotonic()+8;last_send=0;accepted=None
    while time.monotonic()<deadline:
        r.fatal_check();current,last,connected,ack=r.snapshot()
        if connected and time.monotonic()-last_send>=.8:
            c.publish(CONTROL,command,qos=0,retain=False);last_send=time.monotonic()
        if ack and ack.get('trial')==trial['trial'] and ack.get('accepted') and current and ack.get('boot')==current['boot']:
            accepted=ack;break
        time.sleep(.05)
    if accepted is None:
        r.event('trial_skipped_no_ack',trial=trial['trial']);r.set_phase(0,'recovery')
        print('No trial acknowledgement. Do not start the motion yet; recording continues.');return False
    r.event('trial_started',trial=trial,ack=accepted)
    beep();print('GO - RECORDING',flush=True)
    # Bound the physical action by a laptop timer even if the glove disconnects.
    # In the common case this starts milliseconds after the ESP acknowledgement.
    # A delayed ACK is clamped to the remaining ESP interval when it can be observed.
    current,_,_,_=r.snapshot()
    remaining=trial['duration_s']
    if current and current['boot']==accepted['boot']:
        remaining=min(remaining,max(0,(accepted['end_us']-current['timestamp_us'])/1e6))
    end=time.monotonic()+remaining;warned=False;old_boot=accepted['boot'];last_second=-1
    while time.monotonic()<end:
        r.fatal_check();current,last,connected,_=r.snapshot();age=time.monotonic()-last
        if (not connected or age>1) and not warned:
            r.event('live_link_warning',trial=trial['trial'],data_age_s=round(age,3),broker_connected=connected)
            print('LINK PAUSE - still recording; countdown continues.',flush=True);warned=True
        elif connected and age<.5 and warned:
            r.event('live_link_recovered',trial=trial['trial']);print('Live readings recovered.',flush=True);warned=False
        if current and current['boot']!=old_boot:
            print('GLOVE RESTART DETECTED - recording the new boot.',flush=True);old_boot=current['boot']
        seconds=max(0,math.ceil(end-time.monotonic()))
        if seconds!=last_second:print(f'  {seconds} s remaining',flush=True);last_second=seconds
        time.sleep(.1)
    beep();print('STOP - rest your hand.',flush=True);r.event('trial_finished',trial=trial['trial'])
    r.set_phase(0,'recovery');time.sleep(2)
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='172.20.10.2');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--speak',action='store_true')
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'stress_results')
    args=p.parse_args()
    try:import paho.mqtt.client as mqtt
    except ImportError:raise SystemExit('Install paho-mqtt: py -m pip install -r requirements.txt')
    session=uuid.uuid4().hex[:16];folder=args.output/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+session)
    folder.mkdir(parents=True);r=Recorder(folder,session)
    r.trials=[{'trial':i+1,'label':label,'duration_s':seconds,'instruction':instruction} for i,(label,seconds,instruction) in enumerate(PLAN)]
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='glove-stress-'+session)
    c.on_connect=r.on_connect;c.on_disconnect=r.on_disconnect;c.on_message=r.on_message
    c.reconnect_delay_set(min_delay=1,max_delay=5)
    complete=False;error=None;started=False;outcomes=[]
    print('Wireless glove stress test. Keep your existing diagnostic sketch and use battery power.')
    print('Use brisk comfortable motion, without hitting surfaces or deliberately pulling wires.')
    print('Disconnects and restarts are recorded; they do not abort this test. Ctrl+C saves a partial result.')
    try:
        c.connect_async(args.host,args.port,keepalive=5);c.loop_start();started=True
        print('Waiting for live diagnostic samples...')
        if wait_live(r) is None:raise RuntimeError('No live data within 60 seconds. Check battery, Wi-Fi and broker.')
        for trial in r.trials:outcomes.append(run_trial(c,r,trial,args.speak))
        complete=all(outcomes)
    except (KeyboardInterrupt,EOFError):error='Stopped by user.';print('\nSaving partial result.')
    except Exception as e:error=str(e);print('\nTest stopped: '+error)
    finally:
        r.set_phase(0,'ending')
        if started:
            try:
                # Never retain control commands or queue a late motion phase for reconnect.
                if c.is_connected():c.publish(CONTROL,'STOP '+session,qos=0,retain=False).wait_for_publish(timeout=2)
            except Exception:pass
            c.disconnect();c.loop_stop()
        r.event('run_finished',complete=complete,error=error);r.close()
        if r.error:complete=False;error=r.error
        summary=make_summary(r)
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        manifest={'format_version':2,'mode':'motion_stress','session':session,'complete':complete,'error':error,
            'finished_utc':utc_now(),'broker':args.host,'port':args.port,'trials':r.trials,'trial_outcomes':outcomes,
            'local_queue_dropped':r.local_dropped,'sample_hz':50,'imu_ranges':{'accel_g':4,'gyro_deg_s':500},
            'units':{'acceleration':'m/s^2','gyro':'rad/s','flex':'12-bit ADC counts'},
            'recording_scope':'All diagnostic data, including new boots, idle data, link gaps and recovery.',
            'labels':'ESP labels identify acquisition phases. Host labels supply context only for unlabelled/reboot data.'}
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        archive=folder.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for f in folder.iterdir():
                if f.is_file():z.write(f,f.name)
        w=summary['whole_recording']
        print('\n'+('COMPLETE' if complete else 'PARTIAL')+' result saved. Send this ZIP:\n'+str(archive))
        print(f"Boot changes: {w['observed_boot_changes']}; IMU failures: {w['imu_invalid_samples']}; missing samples: {w['missing_sequences']}")
        print(f"Receive gaps >1 s: {len(w['receive_gaps_over_1s'])}; gyro-clipped samples: {w['gyro_clipped_samples']}; new queue drops: {w['new_queue_drops']}")
    return 0 if complete else 1

if __name__=='__main__':raise SystemExit(main())
