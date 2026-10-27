"""Collect ten clean, wearer-confirmed examples per Milo action and ZIP the AI handoff."""
import argparse,collections,csv,hashlib,io,json,random,sys,uuid,zipfile
from datetime import datetime
from pathlib import Path
import numpy as np
from wireless_capture import Recorder,capture,CONTROL
from capture_helpers import announce,utc_now
from dataset_tools import PROFILE,FEATURES,quality,make_calibration,release_candidate,write_clip,load_rows,export_dataset

ROOT=Path(__file__).resolve().parent

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
    print('Was this ONE correct gesture, fully inside the recording?'+extra)
    while True:
        answer=input('[Enter=keep, r=repeat, q=save and stop] ').strip().lower()
        if answer in ['', 'r','q']:return 'keep' if answer=='' else answer
        print('Use Enter, r or q.')

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
            writer.writerow([m['clip_id'],c,m['spoken_phrase_prompt'],False,manifest['participant'],manifest['session_id'],50,m['duration_ms'],100,stem+'.csv',stem+'.json'])
        files['manifest.csv']=table.getvalue().encode('utf-8')
        for name in ['session.json','calibration.json']:files[name]=(folder/name).read_bytes()
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
    print('\nClean training counts:',counts)
    print('COMPLETE' if manifest['complete'] else 'PARTIAL - the requested count has not been completed.')
    if handoff:print('AI handoff ZIP:',handoff)
    else:print('Calibration was not completed; no training ZIP was produced.')
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
        print('Resuming:',folder,'\nResume only with the SAME glove fit/calibration. Start a new collection after removing/refitting the glove.')
        for p in (folder/'clips').glob('*.csv'):
            if not p.with_suffix('.json').is_file():raise ValueError('Incomplete saved CSV/JSON pair: '+str(p))
        m['error']=None;return folder,m
    token=uuid.uuid4().hex[:16];session_id=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+token
    folder=a.output/session_id;(folder/'clips').mkdir(parents=True)
    m={'format_version':2,'session_id':session_id,'session_token':token,'participant':a.participant,'split_role':'train',
       'class_order':[c['id'] for c in cfg['classes']],'class_definitions':cfg,'definition_sha256':digest,'hardware_profile':PROFILE,
       'feature_names':FEATURES,'active_flex_sensors':['thumb','index'],'disabled_sensors':{'middle':'failed; omitted, not imputed'},
       'sample_hz':50,'clip_ms':2000,'target_per_class':a.reps,'random_seed':int(token[:8],16),'started_utc':utc_now(),
       'speech_recorded':False,'capture_notes':'Glove-only personal training. Speak matching Milo phrase naturally around movement. Speech and movement onset are not measured by the prompt.',
       'complete':False,'error':None,'accepted_clips':0,'accepted_per_class':{c['id']:0 for c in cfg['classes']}}
    save_json(folder/'session.json',m);pointer.write_text(session_id,encoding='utf-8');return folder,m

def run(a,cfg):
    folder,m=open_session(a,cfg);classes=m['class_order'];counts=counted(folder,classes)
    if all(v==a.reps for v in counts.values()):finalise(folder,m);return 0
    if any(v>a.reps for v in counts.values()):raise ValueError('Saved dataset exceeds target; start a new collection.')
    import paho.mqtt.client as mqtt
    r=Recorder(folder,m['session_token']);client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='milo-training-'+uuid.uuid4().hex[:12])
    client.on_connect=r.on_connect;client.on_disconnect=r.on_disconnect;client.on_message=r.on_message
    metadata=[json.loads(p.read_text()) for p in (folder/'clips').glob('*.json')]
    trial=max([v['trial'] for v in metadata],default=0);cal=None;stop=False;explained=set()
    print('Direct training collection: '+str(a.reps)+' good examples x '+str(len(classes))+' actions. No pilot.')
    print('2 seconds each: prepare until GO at 1 second; move and finish naturally before STOP at 2 seconds.')
    print('Say the matching phrase around the movement; do not wait for the sentence to finish. Only glove sensors are recorded.')
    print('Session:',folder)
    try:
        client.connect_async(a.host,a.port,keepalive=5);client.loop_start();r.live(60)
        if not m.get('motor_check'):
            print('Motor check: the new firmware gives THREE short buzzes on power-on/reset, then stays OFF.')
            print('If you missed it, press the glove RST button now, wait for it to reconnect, then answer.')
            while True:
                answer=input('Did the motor vibrate? [y=yes, n=no, u=not checked, q=save and stop] ').strip().lower()
                if answer in ['y','n','u','q']:break
                print('Use y, n, u or q.')
            if answer=='q':raise KeyboardInterrupt
            r.live(60)
            m['motor_check']={'source':'wearer_report','result':{'y':'felt_vibration','n':'no_vibration','u':'not_checked'}[answer],'gpio':25,'pattern':'3 x 150ms ON / 150ms OFF; 700ms settle before sampling','checked_utc':utc_now()}
            save_json(folder/'session.json',m)
            if answer=='n':print('Motor reported not working. Sensor collection can continue; motor remains off. Recheck its wiring/power separately.')
        if (folder/'calibration.json').is_file():cal=json.loads((folder/'calibration.json').read_text())
        else:
            poses=[('open','Support your hand, fingers comfortably straight; hold completely still.'),
                   ('fist','Make a comfortable full fist including the thumb; keep still.'),
                   ('ball_grip','Loosely hold an imaginary ball, NOT a tight fist; keep still.')]
            while cal is None:
                readings={}
                for pose,instruction in poses:
                    while True:
                        announce('One-time calibration '+pose+': '+instruction,a.speak)
                        input('Press Enter while holding the pose; record for TWO seconds... ')
                        trial+=1;rows,q,timing=capture(client,r,trial,2000)
                        meta={'kind':'calibration','clip_id':f'{r.token}_{trial:04d}','trial':trial,'pose':pose,'duration_ms':2000,'quality':q,'timing':timing,'accepted':q['usable'] and not q['warnings']}
                        write_clip(folder,meta['clip_id'],rows,meta)
                        if meta['accepted']:readings[pose]=rows;break
                        print('Calibration needs repeating:',q['errors'],q['warnings'])
                        if input('Enter=retry, q=save and stop: ').strip().lower()=='q':raise KeyboardInterrupt
                try:cal=make_calibration(readings,settle_ms=500)
                except ValueError as e:
                    print('Calibration needs repeating:',e)
                    if input('Enter=retry the poses, q=stop: ').strip().lower()=='q':raise KeyboardInterrupt
            save_json(folder/'calibration.json',cal)
        rng=random.Random(m['random_seed']+trial)
        while not stop and any(counts[c]<a.reps for c in classes):
            order=[c for c in cfg['classes'] if counts[c['id']]<a.reps];rng.shuffle(order)
            for c in order:
                action=c['id']
                while counts[action]<a.reps:
                    announce(f'\n{action}: good sample {counts[action]+1}/{a.reps}. '+(c['instruction'] if action not in explained else ''),a.speak)
                    explained.add(action)
                    print('Say:',c['spoken_phrase'],'around the action. Use natural timing and small variations; one gesture only.')
                    input('Press Enter to record; prepare, then move at the GO beep... ')
                    trial+=1
                    if trial>60000:raise RuntimeError('Trial limit reached; start a new session.')
                    rows,q,timing=capture(client,r,trial,2000,1000)
                    candidate=release_candidate(rows,cal,500,1900) if rows and c.get('throw') else None
                    meta={'kind':'gesture','clip_id':f'{r.token}_{trial:04d}','trial':trial,'class_id':action,'variant':action,
                          'repetition':counts[action]+1,'duration_ms':2000,'lead_in_ms':1000,'quality':q,'timing':timing,
                          'spoken_phrase_prompt':c['spoken_phrase'],'speech_recorded':False,'speech_alignment_source':'prompt_only_not_measured',
                          'release_candidate':candidate,'human_confirmed_release':False,'signal_reviewed':False,'accepted':False,
                          'annotations':{'action_onset_ms':None,'release_ms':None,'action_end_ms':None,'source':'unannotated'}}
                    if not q['usable'] or q['warnings']:
                        print('NOT COUNTED - repeat:',q['errors'],q['warnings']);decision='repeat_fault'
                    else:
                        decision=confirm(c.get('throw',False));meta['accepted']=decision=='keep'
                        meta['human_confirmed_release']=bool(c.get('throw') and meta['accepted'])
                    write_clip(folder,meta['clip_id'],rows,meta);r.event('training_attempt',metadata=meta)
                    if meta['accepted']:
                        counts[action]+=1;m['accepted_per_class']=counts.copy();m['accepted_clips']=sum(counts.values());save_json(folder/'session.json',m)
                        print('Saved. Total clean examples:',sum(counts.values()),'/',a.reps*len(classes));break
                    if decision=='q':stop=True;break
                    if decision=='repeat_fault' and input('Enter=repeat this sample, q=save and stop: ').strip().lower()=='q':stop=True;break
                if stop:break
    except (KeyboardInterrupt,EOFError):print('Stopped; saved examples will be retained for resume.')
    except Exception as e:m['error']=str(e);print('Collection stopped:',e)
    finally:
        try:
            if client.is_connected():client.publish(CONTROL,'STOP '+r.token,qos=0,retain=False).wait_for_publish(timeout=2)
        except Exception:pass
        client.disconnect();client.loop_stop();r.close()
        if r.error or r.dropped:m['error']=r.error or 'Laptop capture queue overflow'
        finalise(folder,m)
    return 0 if m['complete'] else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='172.20.10.2');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--participant',default='Nitin');p.add_argument('--reps',type=int,default=10)
    p.add_argument('--output',type=Path,default=ROOT/'datasets')
    g=p.add_mutually_exclusive_group();g.add_argument('--resume',type=Path);g.add_argument('--resume-latest',action='store_true')
    p.add_argument('--speak',action='store_true',help='Speak instructions before each recording; disabled by default')
    a=p.parse_args()
    if not 1<=a.reps<=100:p.error('Use 1..100 good samples per action.')
    cfg=json.loads((ROOT/'gestures.json').read_text(encoding='utf-8'))
    if cfg['clip_ms']!=2000 or cfg['sample_hz']!=50 or cfg['lead_in_ms']!=1000:raise ValueError('This collector requires the shared two-second / 50 Hz protocol.')
    try:return run(a,cfg)
    except (OSError,ValueError,RuntimeError) as e:print('Cannot continue:',e);return 1

if __name__=='__main__':raise SystemExit(main())
