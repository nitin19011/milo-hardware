"""Collect ten clean, wearer-confirmed examples per Milo action and ZIP the AI handoff."""
import copy
import argparse,collections,csv,hashlib,io,json,sys,uuid,zipfile,threading,time
from datetime import datetime
from pathlib import Path
import numpy as np
from wireless_capture import Recorder,capture,CONTROL
from capture_helpers import announce as console_announce,utc_now
from dataset_tools import PROFILE,FEATURES,FINGERS,verify_pose,throw_release_fingers,calibration_report,quality,release_candidate,write_clip,load_rows,export_dataset

ROOT=Path(__file__).resolve().parent
VIEW=None

def show(*values,**kwargs):
    text=' '.join(str(v) for v in values)
    if VIEW:VIEW.message(text)
    else:print(*values,**kwargs)

def ask(prompt,kind='ready'):
    return VIEW.ask(prompt,kind) if VIEW else input(prompt)

def announce(text,speak=False):
    if VIEW:VIEW.message(text)
    else:console_announce(text,speak)

def notify(kind,**data):
    if VIEW:VIEW.update(kind,**data)

def capture_feedback(kind,**data):
    notify(kind,**data)
    if not VIEW and kind in ['prepare','hold','go','stop']:
        print({'prepare':'Get ready...','hold':'Hold still...','go':'GO - perform the gesture','stop':'Recording complete.'}[kind],flush=True)

def fault_message(rows,q):
    notes=[]
    for name,bit in [('Thumb',1),('Index',2),('Middle',4)]:
        if any(r['flex_rail_mask']&bit for r in rows):notes.append(name+' reading reached its minimum/maximum limit.')
    labels={'sample_count_mismatch':'Some readings were missing.','sequence_gap_or_duplicate':'Some readings arrived out of sequence.',
            'incomplete_clip_edges':'The recording was incomplete.','irregular_acquisition':'Sensor timing was irregular.',
            'imu_read_failure':'The motion sensor could not be read.','imu_range_clipping':'The motion exceeded the sensor range.',
            'queue_drops':'The glove lost queued readings.','board_restart':'The glove restarted.',
            'board_restart_during_capture':'The glove restarted.','no_samples':'No readings received.','missing_go_cue':'The GO cue was missed.','missing_finger_release':'The throw needs a BENT-to-NOT-BENT change in at least one finger after GO.'}
    notes.extend(labels.get(e,e.replace('_',' ').capitalize()+'.') for e in q['errors'] if e!='flex_adc_rail')
    if q['warnings']:notes.append('The recording cue was delayed. Please repeat this take.')
    return ' '.join(notes) or 'This take needs repeating.'

def save_json(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');tmp.replace(path)

def eligible_clips(folder):
    """Recheck canonical readings; acceptance alone never overrides a sensor fault."""
    good=[]
    for p in sorted((folder/'clips').glob('*.json')):
        m=json.loads(p.read_text(encoding='utf-8'))
        if m['kind']!='gesture' or not m.get('accepted'):continue
        if not m['quality']['usable'] or m['quality']['warnings']:continue
        rows=load_rows(p.with_suffix('.csv'))
        if quality(rows,m['duration_ms'])['usable']:good.append((p,m))
    return good

def counted(folder,classes):
    result={c:0 for c in classes}
    for _,m in eligible_clips(folder):
        if m['class_id'] not in result:raise ValueError('Unknown class in saved recordings')
        result[m['class_id']]+=1
    return result

def confirm(throw):
    extra=' Include a loose grip, throwing swing AND finger opening.' if throw else ''
    show('Was this ONE correct gesture, fully inside the recording?'+extra)
    while True:
        answer=ask('[Enter=keep, r=repeat, q=save and stop] ','review').strip().lower()
        if answer in ['', 'r','q']:return 'keep' if answer=='' else answer
        show('Use Enter, r or q.')

def write_zip(path,files):
    tmp=path.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    with zipfile.ZipFile(tmp) as z:
        bad=z.testzip()
        if bad:raise RuntimeError('ZIP verification failed: '+bad)
    tmp.replace(path)

def finalise(folder,manifest):
    """The teammate ZIP contains only eligible training examples, never firmware/secrets."""
    classes=manifest['class_order'];counts=counted(folder,classes)
    manifest['accepted_per_class']=counts
    manifest['accepted_clips']=sum(counts.values())
    manifest['complete']=all(n==manifest['target_per_class'] for n in counts.values()) and not manifest.get('error')
    manifest['finished_utc']=utc_now();save_json(folder/'session.json',manifest)
    handoff=None
    if manifest.get('calibration_only'):
        report=folder/'calibration_report.txt'
        archive=folder.parent/('Milo_Calibration_'+manifest['session_id']+'.zip')
        write_zip(archive,{str(p.relative_to(folder)).replace('\\','/'):p.read_bytes() for p in folder.rglob('*') if p.is_file() and p.suffix!='.tmp'})
        notify('finished',counts=counts.copy(),target=manifest['target_per_class'],complete=False,handoff=str(archive),error=manifest.get('error'),calibration_only=True,report=report.read_text(encoding='utf-8') if report.is_file() else 'Calibration not completed.')
        show('Calibration ZIP:',archive)
        return archive
    if (folder/'calibration.json').is_file():
        details=export_dataset([folder],folder/'export')
        if details['accepted_clips']!=sum(counts.values()):raise RuntimeError('Export counts differ from clean sample counts.')
        data=np.load(folder/'export/dataset.npz',allow_pickle=False)
        if any(int(np.sum(data['labels']==c))!=counts[c] for c in classes):raise RuntimeError('Export labels differ from per-action counts.')
        from review_session import build_review
        build_review(folder)
        files={};table=io.StringIO(newline='');writer=csv.writer(table)
        writer.writerow(['clip_id','class_id','spoken_phrase_prompt','speech_recorded','participant','wear_session_id','sample_hz','duration_ms','frames','csv_path','json_path'])
        index=collections.Counter()
        for p,m in eligible_clips(folder):
            c=m['class_id'];index[c]+=1;stem=f'clips/{c}/{c}_{index[c]:02d}'
            files[stem+'.csv']=p.with_suffix('.csv').read_bytes();files[stem+'.json']=p.read_bytes()
            writer.writerow([m['clip_id'],c,m['spoken_phrase_prompt'],False,manifest['participant'],manifest['session_id'],50,m['duration_ms'],m['duration_ms']//20,stem+'.csv',stem+'.json'])
        files['manifest.csv']=table.getvalue().encode('utf-8')
        for name in ['session.json','calibration.json','calibration_report.txt']:files[name]=(folder/name).read_bytes()
        for p in (folder/'export').iterdir():
            if p.is_file():files['export/'+p.name]=p.read_bytes()
        files['README_FOR_AI.txt']=(ROOT/'AI_HANDOFF.txt').read_bytes()
        files['example_load_dataset.py']=(ROOT/'example_load_dataset.py').read_bytes()
        files['export_optional_formats.py']=(ROOT/'export_optional_formats.py').read_bytes()
        files['SHA256SUMS.json']=json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in files.items()},indent=2).encode('utf-8')
        tag='Training' if manifest['complete'] else 'PARTIAL'
        handoff=folder.parent/f'Milo_AI_{tag}_{manifest["session_id"]}.zip'
        write_zip(handoff,files)
    # This separate local archive retains failed attempts for troubleshooting.
    write_zip(folder.with_suffix('.zip'),{str(p.relative_to(folder)).replace('\\','/'):p.read_bytes() for p in folder.rglob('*') if p.is_file() and p.suffix!='.tmp'})
    show('\nClean training counts:',counts)
    show('COMPLETE' if manifest['complete'] else 'PARTIAL - the requested count has not been completed.')
    notify('finished',counts=counts.copy(),target=manifest['target_per_class'],complete=manifest['complete'],handoff=str(handoff) if handoff else None,error=manifest.get('error'))
    if handoff:show('AI handoff ZIP:',handoff)
    else:show('Calibration was not completed; no training ZIP was produced.')
    return handoff

def open_session(a,cfg):
    digest=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
    resume=a.resume
    pointer=a.output/'latest_session.txt'
    if a.resume_latest:
        if not pointer.is_file():raise ValueError('No saved session here. Use START_COLLECTION.bat first.')
        resume=a.output/pointer.read_text(encoding='utf-8').strip()
    if resume:
        folder=resume.resolve();m=json.loads((folder/'session.json').read_text(encoding='utf-8'))
        if m['definition_sha256']!=digest or m['hardware_profile']!=PROFILE:raise ValueError('Saved session uses a different protocol/profile.')
        if m['target_per_class']!=a.reps or m['participant']!=a.participant:raise ValueError('Resume with the same participant and sample target.')
        show('Resuming:',folder,'\nResume only with the SAME glove fit/calibration. Start a new collection after removing/refitting the glove.')
        for p in (folder/'clips').glob('*.csv'):
            if not p.with_suffix('.json').is_file():raise ValueError('Incomplete saved CSV/JSON pair: '+str(p))
        if m.get('collection_order')!='class_blocked':
            m.setdefault('collection_order_history',[]).append({'previous':m.get('collection_order','interleaved'),'new':'class_blocked','existing_accepted_samples':m.get('accepted_clips',0),'changed_utc':utc_now()})
        m['error']=None;m['collection_order']='class_blocked';return folder,m
    token=uuid.uuid4().hex[:16];session_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+token
    folder=a.output/session_id;(folder/'clips').mkdir(parents=True)
    m={'format_version':2,'session_id':session_id,'session_token':token,'participant':a.participant,'split_role':'train',
       'class_order':[c['id'] for c in cfg['classes']],'class_definitions':cfg,'definition_sha256':digest,'hardware_profile':PROFILE,
       'feature_names':FEATURES,'active_flex_sensors':FINGERS,'disabled_sensors':{},
       'sample_hz':50,'clip_ms':cfg['clip_ms'],'calibration_id':cfg['calibration_id'],'target_per_class':a.reps,'random_seed':int(token[:8],16),'started_utc':utc_now(),
       'finger_encoding':{'NOT_BENT':0,'BENT':1},'speech_recorded':False,'capture_notes':'Glove-only personal training. Speak matching Milo phrase naturally around movement. Speech and movement onset are not measured by the prompt.',
       'collection_order':'class_blocked','complete':False,'error':None,'accepted_clips':0,'accepted_per_class':{c['id']:0 for c in cfg['classes']}}
    save_json(folder/'session.json',m);pointer.write_text(session_id,encoding='utf-8');return folder,m

def run(a,cfg):
    folder,m=open_session(a,cfg);m['calibration_only']=getattr(a,'calibration_only',False);classes=m['class_order'];counts=counted(folder,classes)
    if all(v==a.reps for v in counts.values()):finalise(folder,m);return 0
    if any(v>a.reps for v in counts.values()):raise ValueError('Saved dataset exceeds target; start a new collection.')
    import paho.mqtt.client as mqtt
    r=Recorder(folder,m['session_token']);client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='milo-training-'+uuid.uuid4().hex[:12])
    client.on_connect=r.on_connect;client.on_disconnect=r.on_disconnect;client.on_message=r.on_message
    metadata=[json.loads(p.read_text()) for p in (folder/'clips').glob('*.json')]
    trial=max([v['trial'] for v in metadata],default=0);cal=None;stop=False
    r.feedback=capture_feedback
    if VIEW:r.cancel_check=VIEW.check_cancel
    notify('connecting',counts=counts.copy(),target=a.reps)
    show('Direct training collection: '+str(a.reps)+' good examples x '+str(len(classes))+' actions. No pilot.')
    show('3 seconds each: prepare until GO at 1 second; move and finish naturally before STOP at 3 seconds.')
    show('Say the matching phrase around the movement; do not wait for the sentence to finish. Only glove sensors are recorded.')
    show('Session:',folder)
    try:
        client.connect_async(a.host,a.port,keepalive=5);client.loop_start();r.live(60)
        existing_cal=(folder/'calibration.json').is_file()
        cal=json.loads(((folder/'calibration.json') if existing_cal else ROOT/'sensor_settings.json').read_text(encoding='utf-8'))
        # Four seconds of fit checks, not another calibration or training pilot.
        # Firmware states are authoritative, so both training and live inference use identical hysteresis.
        checks=[('open','Relax all three monitored fingers and keep your hand still; they should read NOT_BENT.'),
                ('fist','Make a comfortable fist; all three monitored fingers should read BENT.')]
        for pose,instruction in checks:
            while True:
                notify('calibration',pose=pose,instruction=instruction)
                ask('Hold the pose, then Enter to check for 2 seconds... ')
                trial+=1;rows,q,timing=capture(client,r,trial,2000)
                failures=verify_pose(rows,pose) if q['usable'] else []
                if failures:q['usable']=False;q['errors'].append('incorrect_bend_state: '+', '.join(failures))
                if pose=='open' and q['usable']:
                    steady=[v for v in rows if v['elapsed_ms']>=500]
                    if max(float(np.std([v[k] for v in steady])) for k in FEATURES[3:6])>.04:
                        q['usable']=False;q['errors'].append('Hold your hand still for the open-hand check.')
                    elif not existing_cal:cal['gyro_bias_rad_s']={k:float(np.median([v[k] for v in steady])) for k in FEATURES[3:6]}
                meta={'kind':'fit_check','clip_id':f'{r.token}_{trial:04d}','trial':trial,'pose':pose,'duration_ms':2000,'quality':q,'timing':timing,'accepted':q['usable'] and not q['warnings']}
                write_clip(folder,meta['clip_id'],rows,meta)
                if meta['accepted']:break
                message=fault_message(rows,q);notify('fault',message=message);show('Repeat fit check:',message)
                if ask('Enter=retry, q=save and stop: ','retry').strip().lower()=='q':raise KeyboardInterrupt
        cal['fit_checked_utc']=utc_now();cal['calibration_id']=cfg['calibration_id'];save_json(folder/'calibration.json',cal)
        (folder/'calibration_report.txt').write_text(calibration_report(cal),encoding='utf-8')
        m['finger_encoding']={'NOT_BENT':0,'BENT':1}
        m['state_thresholds']={k:{n:cal['flex_diagnostics'][k][n] for n in ['bend_threshold','release_threshold','bend_increases']} for k in FINGERS}
        save_json(folder/'session.json',m)
        # Finish one gesture before moving to the next; preserve existing saved takes on resume.
        for class_index,c in enumerate(cfg['classes']):
            action=c['id']
            if counts[action]>=a.reps:continue
            notify('gesture',action=action,instruction=c['instruction'],phrase=c['spoken_phrase'],counts=counts.copy(),target=a.reps,index=class_index)
            announce(f"{action}: collect samples {counts[action]+1} to {a.reps}. {c['instruction']}",a.speak)
            need_ready=True
            while counts[action]<a.reps:
                notify('sample',action=action,number=counts[action]+1,counts=counts.copy(),target=a.reps)
                show(f"{action} | sample {counts[action]+1}/{a.reps} | total {sum(counts.values())}/{a.reps*len(classes)}")
                if need_ready:ask('Press Enter to record this sample... ')
                need_ready=True
                trial+=1
                if trial>60000:raise RuntimeError('Trial limit reached; start a new session.')
                rows,q,timing=capture(client,r,trial,cfg['clip_ms'],cfg['lead_in_ms'])
                candidate=release_candidate(rows,cal,cfg['lead_in_ms'],cfg['clip_ms']-100) if rows and c.get('throw') else None
                release_fingers=throw_release_fingers(rows) if c.get('throw') else []
                if c.get('throw') and q['usable'] and len(release_fingers)<1:
                    q['usable']=False;q['errors'].append('missing_finger_release')
                meta={'kind':'gesture','clip_id':f'{r.token}_{trial:04d}','trial':trial,'class_id':action,'variant':action,
                      'repetition':counts[action]+1,'duration_ms':cfg['clip_ms'],'lead_in_ms':cfg['lead_in_ms'],'calibration_id':cfg['calibration_id'],'quality':q,'timing':timing,
                      'spoken_phrase_prompt':c['spoken_phrase'],'speech_recorded':False,'speech_alignment_source':'prompt_only_not_measured',
                      'release_fingers':release_fingers,'release_candidate':candidate,'human_confirmed_release':False,'signal_reviewed':False,'accepted':False,
                      'annotations':{'action_onset_ms':None,'release_ms':None,'action_end_ms':None,'source':'unannotated'}}
                if not q['usable'] or q['warnings']:
                    message=fault_message(rows,q);notify('fault',message=message)
                    show('Not saved:',message);decision='repeat_fault'
                else:
                    decision=confirm(c.get('throw',False));meta['accepted']=decision=='keep'
                    meta['human_confirmed_release']=bool(c.get('throw') and meta['accepted'])
                write_clip(folder,meta['clip_id'],rows,meta);r.event('training_attempt',metadata=meta)
                if meta['accepted']:
                    counts[action]+=1;m['accepted_per_class']=counts.copy();m['accepted_clips']=sum(counts.values());save_json(folder/'session.json',m)
                    notify('saved',action=action,counts=counts.copy(),target=a.reps)
                    show(f"Saved {action}: {counts[action]}/{a.reps} | total {sum(counts.values())}/{a.reps*len(classes)}")
                elif decision=='q':stop=True;break
                elif decision=='repeat_fault':
                    if ask('Enter=repeat this sample, q=save and stop: ','retry').strip().lower()=='q':stop=True;break
                    need_ready=False
                else:need_ready=False
            if stop:break
    except (KeyboardInterrupt,EOFError):show('Stopped; saved examples will be retained for resume.')
    except Exception as e:m['error']=str(e);show('Collection stopped:',e)
    finally:
        try:
            if client.is_connected():client.publish(CONTROL,'STOP '+r.token,qos=0,retain=False).wait_for_publish(timeout=2)
        except Exception:pass
        client.disconnect();client.loop_stop();r.close()
        if r.error or r.dropped:m['error']=r.error or 'Laptop capture queue overflow'
        notify('saving')
        finalise(folder,m)
    return 0 if m['complete'] or (m['calibration_only'] and cal is not None and not m.get('error')) else 1

def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='172.20.10.2');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--participant',default='Nitin');p.add_argument('--reps',type=int,default=10)
    p.add_argument('--output',type=Path,default=ROOT/'datasets')
    g=p.add_mutually_exclusive_group();g.add_argument('--resume',type=Path);g.add_argument('--resume-latest',action='store_true')
    p.set_defaults(calibration_only=False)
    p.add_argument('--speak',action='store_true',help='Speak instructions before each recording; disabled by default')
    a=p.parse_args(argv)
    if not 1<=a.reps<=100:p.error('Use 1..100 good samples per action.')
    cfg=json.loads((ROOT/'gestures.json').read_text(encoding='utf-8'))
    if cfg['clip_ms']!=3000 or cfg['sample_hz']!=50 or cfg['lead_in_ms']!=1000:raise ValueError('This collector requires the shared three-second / 50 Hz protocol.')
    return a,cfg

def main():
    a,cfg=parse_args()
    try:return run(a,cfg)
    except (OSError,ValueError,RuntimeError) as e:show('Cannot continue:',e);return 1

if __name__=='__main__':raise SystemExit(main())
