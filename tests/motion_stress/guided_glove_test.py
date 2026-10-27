"""Guided battery-powered glove test; collect labelled MQTT data into one ZIP."""
import argparse
import base64
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import statistics
import subprocess
import threading
import time
import uuid
import zipfile

DATA = 'diagnostic/glove/data'
STATUS = 'diagnostic/glove/status'
ACK = 'diagnostic/glove/ack'
CONTROL = 'diagnostic/glove/control'
FLEX = ('thumb', 'index', 'middle')
AXES = ('ax', 'ay', 'az', 'gx', 'gy', 'gz')
FIELDS = ['received_utc','trial_label','version','boot','session','trial','seq',
          'timestamp_us','elapsed_ms','thumb','index','middle','thumb_min','thumb_max',
          'index_min','index_max','middle_min','middle_max','imu_ok','raw_ax','raw_ay',
          'raw_az','raw_gx','raw_gy','raw_gz',*AXES,'temp_c','imu_errors','queue_dropped','rssi_dbm']
# Each Enter gives time to get into position, followed by a three-second countdown.
TRIALS = [
 ('open_baseline',12,'Rest your forearm on a table. Palm down, fingers comfortably straight. Keep still.'),
 ('thumb_bent',8,'Bend only your thumb comfortably. Keep index and middle straight; keep your wrist still.'),
 ('thumb_release',5,'Straighten all fingers again. Keep the hand still.'),
 ('index_bent',8,'Bend only the index finger comfortably. Keep thumb and middle straight; wrist still.'),
 ('index_release',5,'Straighten all fingers again. Keep the hand still.'),
 ('middle_bent',8,'Bend only the middle finger comfortably. Keep thumb and index straight; wrist still.'),
 ('middle_release',5,'Straighten all fingers again. Keep the hand still.'),
 ('fist',8,'Make a comfortable fist, including the thumb. Keep the wrist still. Do not force the flex sensors.'),
 ('open_after_fist',8,'Open the hand and hold all fingers straight. Keep still.'),
 ('thumb_cycles',12,'Keep wrist, index and middle still. Alternate thumb straight for 2 seconds, bent for 2 seconds, three times.'),
 ('index_cycles',12,'Keep wrist, thumb and middle still. Alternate index straight for 2 seconds, bent for 2 seconds, three times.'),
 ('middle_cycles',12,'Keep wrist, thumb and index still. Alternate middle straight for 2 seconds, bent for 2 seconds, three times.'),
 ('imu_palm_up',10,'Support your hand with palm facing up. Keep fingers straight and the hand completely still.'),
 ('imu_palm_down',10,'Support your hand with palm facing down. Keep fingers straight and the hand completely still.'),
 ('imu_hand_edge',10,'Hold your hand on its side, thumb pointing upwards. Keep fingers straight and hold still.'),
 ('imu_wrist_pitch',10,'With fingers straight, slowly tilt the hand up and down at the wrist several times. Avoid impacts.'),
 ('imu_forearm_roll',10,'With fingers straight, slowly turn palm up then palm down several times.'),
 ('imu_side_to_side',10,'With fingers straight, gently sweep the hand left and right several times.'),
 ('final_still',12,'Return to the initial palm-down supported position. Straighten all fingers and keep completely still.'),
]

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def stats(values):
    a=[float(v) for v in values if isinstance(v,(int,float)) and math.isfinite(v)]
    if not a:return None
    return {'n':len(a),'mean':statistics.mean(a),'std':statistics.pstdev(a),
            'min':min(a),'max':max(a),'median':statistics.median(a)}

def summarise(samples, trials):
    output={'note':'Screening measurements, not a hardware pass/fail certification.', 'trials':[]}
    for trial in trials:
        rows=[r for r in samples if r.get('trial')==trial['trial']]
        # Settle the initial pose for 1 s before assessing static readings.
        stable=[r for r in rows if r.get('elapsed_ms',0)>=1000]
        valid=[r for r in stable if r.get('imu_ok') is True]
        gaps=[]
        for a,b in zip(rows,rows[1:]):
            if a.get('boot')==b.get('boot'):
                gaps.append(max(0,b['seq']-a['seq']-1))
        acc=[math.sqrt(sum(r[k]**2 for k in ('ax','ay','az'))) for r in valid]
        gyro=[math.sqrt(sum(r[k]**2 for k in ('gx','gy','gz'))) for r in valid]
        result={**trial,'received_samples':len(rows),'expected_approx_samples':trial['duration_s']*50,
                'missing_between_received_sequences':sum(gaps),
                'imu_invalid_samples':sum(r.get('imu_ok') is not True for r in rows),
                'span_s':(rows[-1]['timestamp_us']-rows[0]['timestamp_us'])/1e6 if len(rows)>1 else 0,
                'flex':{k:stats(r[k] for r in stable) for k in FLEX},
                'adc_batch_span':{k:stats(r[k+'_max']-r[k+'_min'] for r in stable) for k in FLEX},
                'axes':{k:stats(r[k] for r in valid) for k in AXES},
                'acceleration_magnitude_m_s2':stats(acc),'gyro_magnitude_rad_s':stats(gyro),
                'rssi_dbm':stats(r['rssi_dbm'] for r in rows),
                'timestamp_intervals_ms':stats((b['timestamp_us']-a['timestamp_us'])/1000 for a,b in zip(rows,rows[1:]))}
        result['warnings']=[]
        if len(rows)<trial['duration_s']*50*.9:result['warnings'].append('Fewer than 90% of expected samples received; repeat this trial.')
        if result['imu_invalid_samples']:result['warnings'].append('Checked I2C reads failed during this trial.')
        for k in FLEX:
            clipped=sum(r[k]<=20 or r[k]>=4075 for r in rows)
            if clipped:result['warnings'].append(f'{k}: {clipped} ADC readings near a rail; check divider/wiring.')
        if any(abs(r.get('raw_'+k,0))>=32700 for r in valid for k in AXES):
            result['warnings'].append('IMU range clipping detected.')
        output['trials'].append(result)
    # Compare isolated bends with the initial open baseline, including cross-talk.
    by_label={r['label']:r for r in output['trials']}
    baseline=by_label.get('open_baseline',{}).get('flex',{})
    comparisons={}
    for finger in FLEX:
        bent=by_label.get(finger+'_bent',{}).get('flex',{})
        comparisons[finger]={}
        for channel in FLEX:
            if baseline.get(channel) and bent.get(channel):
                change=bent[channel]['median']-baseline[channel]['median']
                comparisons[finger][channel+'_median_change']=change
                if channel==finger:
                    comparisons[finger]['bend_direction']='increases' if change>0 else 'decreases' if change<0 else 'unchanged'
                    comparisons[finger]['open_bend_range_overlap']=not (baseline[channel]['max']<bent[channel]['min'] or bent[channel]['max']<baseline[channel]['min'])
    output['isolated_finger_comparisons']=comparisons
    return output

class Recorder:
    def __init__(self, folder, session):
        self.folder=folder;self.session=session;self.records=queue.Queue(maxsize=20000)
        self.lock=threading.Lock();self.last_sample=None;self.last_receive=0;self.boot=None
        self.ack=None;self.connected=False;self.trials=[];self.samples=[];self.local_dropped=0
        self.error=None;self.done=threading.Event()
        self.worker=threading.Thread(target=self.write_records,daemon=True);self.worker.start()
    def enqueue(self, item):
        try:self.records.put_nowait(item)
        except queue.Full:self.local_dropped+=1
    def event(self, kind, **values):
        self.enqueue({'kind':kind,'utc':utc_now(),**values})
    def on_connect(self,c,u,flags,reason,properties):
        if reason.is_failure:
            self.event('broker_connect_failed',reason=str(reason));return
        self.connected=True;c.subscribe([(DATA,0),(ACK,1),(STATUS,1)])
        self.event('broker_connected')
    def on_disconnect(self,c,u,flags,reason,properties):
        self.connected=False;self.event('broker_disconnected',reason=str(reason))
    def on_message(self,c,u,msg):
        received=utc_now()
        try:
            if len(msg.payload)>2048:raise ValueError('Oversized diagnostic message')
            data=json.loads(msg.payload)
            if not isinstance(data,dict):raise ValueError('Expected JSON object')
            if msg.topic==DATA:
                if msg.retain:return
                required=['version','boot','session','trial','seq','timestamp_us','elapsed_ms','imu_ok',*FLEX,'rssi_dbm']
                if data.get('version')!=1 or any(k not in data for k in required):raise ValueError('Unexpected sample schema')
                for k in FLEX:
                    if type(data[k]) is not int or not 0<=data[k]<=4095:raise ValueError('Invalid ADC value')
                if data['imu_ok']:
                    if any(not isinstance(data.get(k),(int,float)) or not math.isfinite(data[k]) for k in AXES):raise ValueError('Invalid IMU value')
                with self.lock:
                    self.last_sample=data;self.last_receive=time.monotonic()
                self.enqueue({'kind':'sample','received_utc':received,'data':data})
            elif msg.topic==ACK:
                if not msg.retain and data.get('session')==self.session:
                    with self.lock:self.ack=data
                    self.event('ack',data=data)
            else:self.event('glove_status',retained=msg.retain,data=data)
        except (ValueError,TypeError,KeyError) as e:self.event('invalid_message',error=str(e))
    def write_records(self):
        try:
            with (self.folder/'samples.csv').open('w',newline='',encoding='utf-8') as cf, \
                 (self.folder/'raw_samples.jsonl').open('w',encoding='utf-8') as rf, \
                 (self.folder/'events.jsonl').open('w',encoding='utf-8') as ef:
                writer=csv.DictWriter(cf,fieldnames=FIELDS);writer.writeheader()
                while not self.done.is_set() or not self.records.empty():
                    try:item=self.records.get(timeout=.2)
                    except queue.Empty:continue
                    if item['kind']=='sample':
                        row=item['data']
                        rf.write(json.dumps(item)+'\n')
                        # Only record this run in CSV; idle trial 0 remains useful context.
                        if row.get('session')==self.session:
                            label=next((t['label'] for t in self.trials if t['trial']==row['trial']),'idle')
                            writer.writerow({**{k:row.get(k) for k in FIELDS},'received_utc':item['received_utc'],'trial_label':label})
                            if row.get('trial',0)>0:self.samples.append(row)
                        cf.flush();rf.flush()
                    else:ef.write(json.dumps(item)+'\n');ef.flush()
        except Exception as e:self.error=str(e)
    def health(self,boot):
        if self.error:raise RuntimeError('Recording failed: '+self.error)
        if self.local_dropped:raise RuntimeError('Laptop recording queue overflowed; partial data saved.')
        with self.lock:s=self.last_sample;age=time.monotonic()-self.last_receive
        if not self.connected or age>3:raise RuntimeError('Wireless data stopped for more than 3 seconds. Partial data saved; reconnect and rerun.')
        if s and s['boot']!=boot:raise RuntimeError('Glove restarted during the test. Partial data saved; rerun.')
    def close(self):
        self.done.set();self.worker.join(timeout=15)
        if self.worker.is_alive():self.error='Recording worker failed to finish.'

def announce(text, speak=False):
    print(text,flush=True)
    if speak:
        # Pass text as an argument, never interpolate it into shell code.
        encoded_text=base64.b64encode(text.encode('utf-8')).decode('ascii')
        code="Add-Type -AssemblyName System.Speech; $v=New-Object System.Speech.Synthesis.SpeechSynthesizer; $v.Speak([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+encoded_text+"')))"
        encoded_code=base64.b64encode(code.encode('utf-16le')).decode('ascii')
        try:
            subprocess.run(['powershell','-NoProfile','-EncodedCommand',encoded_code],
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        except (OSError,subprocess.SubprocessError):print('(Speech unavailable; use the displayed prompt.)')

def beep():
    try:
        import winsound
        winsound.Beep(1000,180)
    except (ImportError,RuntimeError):pass

def run_trial(client,r,trial,boot,speak):
    print(f"\n[{trial['trial']}/{len(TRIALS)}] {trial['label']} - {trial['duration_s']} seconds")
    announce(trial['instruction'],speak)
    input('Press ENTER when ready, then get into position during the countdown... ')
    r.health(boot)
    for n in (3,2,1):print(n,flush=True);time.sleep(1)
    r.health(boot)
    command=f"GO {r.session} {trial['trial']} {trial['duration_s']*1000}"
    with r.lock:r.ack=None
    deadline=time.monotonic()+6;last_send=0
    while time.monotonic()<deadline:
        r.health(boot)
        if time.monotonic()-last_send>=.8:
            client.publish(CONTROL,command,qos=1,retain=False);last_send=time.monotonic()
        with r.lock:ack=r.ack
        if ack and ack.get('trial')==trial['trial'] and ack.get('boot')==boot:
            if not ack.get('accepted'):raise RuntimeError('Glove is busy; partial data saved.')
            break
        time.sleep(.03)
    else:raise RuntimeError('Glove did not acknowledge the trial command.')
    r.event('trial_started',trial=trial,ack=ack);beep();print('RECORDING',flush=True)
    end_us=ack['end_us'];last_second=-1
    # Use ESP timestamps, not a guessed laptop/ESP clock offset.
    timeout=time.monotonic()+trial['duration_s']+8
    while time.monotonic()<timeout:
        r.health(boot)
        with r.lock:s=r.last_sample
        if s['timestamp_us']>=end_us:break
        remaining=max(0,math.ceil((end_us-s['timestamp_us'])/1e6))
        if remaining!=last_second:print(f'  {remaining} s remaining',flush=True);last_second=remaining
        time.sleep(.05)
    else:raise RuntimeError('Trial did not finish within its allowed time.')
    # Allow queued QoS 0 samples to reach the recording thread before next trial.
    time.sleep(.25);beep();r.event('trial_finished',trial=trial['trial']);print('DONE - relax your hand.',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1',help='Broker address; localhost works when running on the broker laptop.')
    parser.add_argument('--port',type=int,default=1883)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'test_results')
    parser.add_argument('--speak',action='store_true',help='Read instructions aloud on Windows.')
    args=parser.parse_args()
    try:import paho.mqtt.client as mqtt
    except ImportError:raise SystemExit('Install the receiver dependency first: py -m pip install "paho-mqtt>=2,<3"')
    session=uuid.uuid4().hex[:16]
    folder=args.output/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+session)
    folder.mkdir(parents=True)
    r=Recorder(folder,session)
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='glove-test-'+session)
    client.on_connect=r.on_connect;client.on_disconnect=r.on_disconnect;client.on_message=r.on_message
    complete=False;failure=None;started=False
    print('Wireless glove test. Leave USB disconnected during the exercises.\n',flush=True)
    print('Keep the laptop awake. Use the same Wi-Fi/hotspot as the glove.\nResults: '+str(folder),flush=True)
    try:
        client.connect(args.host,args.port,keepalive=10);client.loop_start();started=True
        print('Waiting for LIVE diagnostic firmware data (up to 60 seconds)...',flush=True)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            with r.lock:s=r.last_sample;age=time.monotonic()-r.last_receive
            if r.connected and s and age<1:break
            if r.error:raise RuntimeError(r.error)
            time.sleep(.1)
        else:raise RuntimeError('No live samples. Check board power, Wi-Fi, broker, and diagnostic sketch upload.')
        boot=s['boot'];r.boot=boot
        print(f"Glove connected. RSSI {s['rssi_dbm']} dBm. IMU read OK: {s['imu_ok']}")
        if not s['imu_ok']:print('IMU currently unreadable; this test will still record flex and IMU fault evidence.')
        r.trials=[{'trial':i+1,'label':name,'duration_s':seconds,'instruction':instruction}
                  for i,(name,seconds,instruction) in enumerate(TRIALS)]
        for trial in r.trials:run_trial(client,r,trial,boot,args.speak)
        complete=True
    except (KeyboardInterrupt,EOFError):failure='Stopped by user.';print('\nStopped; preserving partial data.')
    except Exception as e:failure=str(e);print('\nTest stopped: '+failure)
    finally:
        if started:
            try:client.publish(CONTROL,'STOP '+session,qos=1,retain=False).wait_for_publish(timeout=2)
            except Exception:pass
            client.disconnect();client.loop_stop()
        r.event('run_finished',complete=complete,error=failure)
        r.close()
        if r.error:complete=False;failure=r.error
        manifest={'format_version':1,'session':session,'boot':r.boot,'complete':complete,
                  'error':failure,'finished_utc':utc_now(),'broker':args.host,'port':args.port,
                  'units':{'acceleration':'m/s^2','gyro':'rad/s','flex':'12-bit ADC counts'},
                  'local_queue_dropped':r.local_dropped,'sample_hz':50,'trials':r.trials}
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        summary=summarise(r.samples,r.trials)
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        archive=folder.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in folder.iterdir():
                if p.is_file():z.write(p,p.name)
        print('\n'+('COMPLETE' if complete else 'PARTIAL')+' test saved. Send this ZIP for review:\n'+str(archive))
        for trial in summary['trials']:
            for warning in trial['warnings']:print(trial['label']+': '+warning)
    return 0 if complete else 1

if __name__=='__main__':raise SystemExit(main())
