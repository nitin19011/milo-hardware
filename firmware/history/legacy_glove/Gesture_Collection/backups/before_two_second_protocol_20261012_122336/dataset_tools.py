"""Data schema, quality checks, calibration and portable training exports."""
import argparse,csv,json,math,zipfile
from pathlib import Path
import numpy as np
PROFILE='mpu6050_16g_2000dps_21hz_flex8avg_50hz_v1'
FEATURES=['ax','ay','az','gx','gy','gz','thumb','index','middle']
FINGERS=['thumb','index','middle']
COLUMNS=['seq','timestamp_us','elapsed_ms','boot_id',*FEATURES,'imu_valid','flex_rail_mask','imu_errors','queue_dropped',
         'raw_ax','raw_ay','raw_az','raw_gx','raw_gy','raw_gz','rssi_dbm']

def flatten(data):
    if data.get('type')!='hand_sample' or data.get('hardware_profile')!=PROFILE:
        raise ValueError('Upload the updated MBF_v1 collection firmware first (16 g / 2000 deg/s profile).')
    row={k:data[k] for k in ['seq','timestamp_us','boot_id','rssi_dbm']}
    row.update({k:data['imu'][k] for k in FEATURES[:6]})
    row.update({k:data['flex_raw'][k] for k in FINGERS})
    row.update({'imu_valid':bool(data['imu']['valid']),**data['quality'],
                'elapsed_ms':data['collection']['elapsed_ms']})
    for name,value in zip(['raw_ax','raw_ay','raw_az','raw_gx','raw_gy','raw_gz'],data['imu_raw']):row[name]=value
    for k in FEATURES:
        if not isinstance(row[k],(int,float)) or not math.isfinite(row[k]):raise ValueError('Non-finite sensor reading')
    if any(type(row[k]) is not int or not 0<=row[k]<=4095 for k in FINGERS):raise ValueError('Invalid ADC reading')
    return row

def quality(rows,duration_ms):
    hard=[];notes=[]
    if not rows:return {'usable':False,'errors':['no_samples'],'warnings':[],'n':0}
    if len({r['boot_id'] for r in rows})!=1:hard.append('board_restart')
    elapsed=np.array([r['elapsed_ms'] for r in rows]);seq=np.array([r['seq'] for r in rows])
    if len(rows)!=duration_ms//20:hard.append('sample_count_mismatch')
    if np.any(np.diff(seq)!=1):hard.append('sequence_gap_or_duplicate')
    if elapsed[0]>20 or elapsed[-1]<duration_ms-21:hard.append('incomplete_clip_edges')
    if np.any(np.diff(elapsed)>40) or np.any(np.diff(elapsed)<=0):hard.append('irregular_acquisition')
    invalid=sum(not r['imu_valid'] for r in rows)
    rail=sum(r['flex_rail_mask']!=0 for r in rows)
    clipping=sum(any(abs(r['raw_'+k])>=32700 for k in FEATURES[:6]) for r in rows)
    if invalid:hard.append('imu_read_failure')
    if rail:hard.append('flex_adc_rail')
    if clipping:hard.append('imu_range_clipping')
    if rows[-1]['queue_dropped']!=rows[0]['queue_dropped']:hard.append('queue_drops')
    return {'usable':not hard,'errors':hard,'warnings':notes,'n':len(rows),'imu_invalid':invalid,
            'rail_samples':rail,'clipped_samples':clipping,'first_ms':int(elapsed[0]),'last_ms':int(elapsed[-1])}

def make_calibration(clips):
    # Poses are unlabeled per-wear calibration, never a global fit across evaluation gestures.
    stats={}
    for label,rows in clips.items():
        steady=[r for r in rows if r['elapsed_ms']>=1000]
        if not steady:raise ValueError('Missing calibration pose: '+label)
        stats[label]={k:float(np.median([r[k] for r in steady])) for k in FEATURES}
        if label in ['open','still']:
            noise=max(float(np.std([r[k] for r in steady])) for k in FEATURES[3:6])
            if noise>.04:raise ValueError('Hold still during open-hand calibration; gyro variation was too large.')
    open_=stats['open'];closed=stats['fist']
    spans={k:closed[k]-open_[k] for k in FINGERS}
    if any(abs(v)<100 for v in spans.values()):raise ValueError('A flex calibration span is under 100 counts. Check finger placement and sensor response.')
    return {'version':1,'open':{k:open_[k] for k in FINGERS},'fist':{k:closed[k] for k in FINGERS},
            'ball_grip':{k:stats['ball_grip'][k] for k in FINGERS},'span':spans,
            'gyro_bias_rad_s':{k:open_[k] for k in FEATURES[3:6]},
            'normalisation':'(raw - session open median) / (session fist median - session open median); not clipped',
            'pose_medians':stats}

def calibrate(matrix,cal):
    a=np.asarray(matrix,dtype=np.float32).copy()
    for i,k in enumerate(FEATURES[3:6],3):a[:,i]-=cal['gyro_bias_rad_s'][k]
    for i,k in enumerate(FINGERS,6):a[:,i]=(a[:,i]-cal['open'][k])/cal['span'][k]
    return a

def release_candidate(rows,cal):
    # This is review assistance, never automatically promoted to ground-truth annotation.
    a=calibrate([[r[k] for k in FEATURES] for r in rows],cal)
    t=np.array([r['elapsed_ms'] for r in rows]);score=np.median(a[:,6:9],axis=1)
    candidates=[]
    for i in range(5,len(rows)-5):
        if not 1000<=t[i]<=4500:continue
        before=float(np.median(score[i-5:i]));after=float(np.median(score[i:i+5]))
        if before-after>.12 and after<before*.75:
            candidates.append((before-after,int(t[i])))
    if not candidates:return None
    drop,ms=max(candidates)
    return {'elapsed_ms':ms,'normalised_drop':round(drop,3),'source':'heuristic_only','human_confirmed':False}

def write_clip(folder,clip_id,rows,metadata):
    clips=folder/'clips';clips.mkdir(exist_ok=True)
    path=clips/(clip_id+'.csv')
    with path.open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS);w.writeheader()
        for r in rows:w.writerow({k:r.get(k) for k in COLUMNS})
    path.with_suffix('.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return path

def load_rows(path):
    with path.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        for k in COLUMNS:
            if k=='boot_id':continue
            if k=='imu_valid':r[k]=r[k].lower()=='true'
            elif k in FEATURES:r[k]=float(r[k])
            else:r[k]=int(r[k])
    return rows

def export_dataset(folders,destination):
    destination.mkdir(parents=True,exist_ok=True)
    accepted=[];excluded=[];classes=None;session_roles={};definition=None
    for folder in folders:
        manifest=json.loads((folder/'session.json').read_text(encoding='utf-8'))
        current=manifest['class_order']
        if classes is None:classes=current
        if classes!=current:raise ValueError('Different class definitions/orders; review before combining sessions.')
        if definition is None:definition=manifest['definition_sha256']
        if definition!=manifest['definition_sha256']:raise ValueError('Gesture definitions changed between sessions; do not merge silently.')
        cal=json.loads((folder/'calibration.json').read_text())
        session_roles[manifest['session_id']]=manifest.get('split_role','unassigned')
        for meta_path in sorted((folder/'clips').glob('*.json')):
            m=json.loads(meta_path.read_text());
            if m['kind']!='gesture':continue
            if not m.get('accepted') or not m['quality']['usable']:
                excluded.append({'clip_id':m['clip_id'],'quality':m['quality'],'accepted':m.get('accepted')});continue
            if m['quality']['warnings'] and not m.get('signal_reviewed',False):
                excluded.append({'clip_id':m['clip_id'],'reason':'manual_signal_review_required','warnings':m['quality']['warnings']});continue
            rows=load_rows(meta_path.with_suffix('.csv'))
            q=quality(rows,m['duration_ms'])
            if not q['usable']:excluded.append({'clip_id':m['clip_id'],'quality':q});continue
            time_=np.array([r['elapsed_ms'] for r in rows])
            values=np.array([[r[k] for k in FEATURES] for r in rows],dtype=np.float32)
            grid=np.arange(0,6000,20)
            # At most 19 ms edge hold; no internal losses allowed by the quality gate.
            regular=np.column_stack([np.interp(grid,time_,values[:,j]) for j in range(9)]).astype(np.float32)
            accepted.append((m,manifest,regular,calibrate(regular,cal),cal))
    if classes is None:raise ValueError('No sessions supplied')
    n=len(accepted)
    X=np.stack([a[2] for a in accepted]) if n else np.empty((0,300,9),dtype=np.float32)
    Xc=np.stack([a[3] for a in accepted]) if n else np.empty((0,300,9),dtype=np.float32)
    labels=np.array([a[0]['class_id'] for a in accepted],dtype='U40')
    y=np.array([classes.index(v) for v in labels],dtype=np.int64)
    groups=np.array([a[1]['session_id'] for a in accepted],dtype='U40')
    clip_ids=np.array([a[0]['clip_id'] for a in accepted],dtype='U64')
    roles=np.array([a[1].get('split_role','unassigned') for a in accepted],dtype='U16')
    np.savez_compressed(destination/'dataset.npz',X_raw=X,X_session_calibrated=Xc,
        X_raw_channels_first=X.transpose(0,2,1),X_calibrated_channels_first=Xc.transpose(0,2,1),
        X_action_raw=X[:,50:200,:],X_action_calibrated=Xc[:,50:200,:],y=y,labels=labels,
        classes=np.array(classes),feature_names=np.array(FEATURES),session_ids=groups,clip_ids=clip_ids,split_roles=roles,
        train_indices=np.flatnonzero(roles=='train'),validation_indices=np.flatnonzero(roles=='validation'),test_indices=np.flatnonzero(roles=='test'))
    for name,a in [('X_raw',X),('X_session_calibrated',Xc),('y',y),('labels',labels),('session_ids',groups)]:np.save(destination/(name+'.npy'),a)
    with (destination/'all_samples.csv').open('w',newline='',encoding='utf-8') as f, (destination/'clips.jsonl').open('w',encoding='utf-8') as jf:
        w=csv.writer(f);w.writerow(['clip_id','class_id','participant','session_id','split_role','elapsed_ms',*FEATURES])
        for m,manifest,raw,calibrated,cal in accepted:
            for i,row in enumerate(raw):w.writerow([m['clip_id'],m['class_id'],manifest['participant'],manifest['session_id'],manifest.get('split_role','unassigned'),i*20,*row])
            jf.write(json.dumps({'clip_id':m['clip_id'],'class_id':m['class_id'],'session_id':manifest['session_id'],
                 'participant':manifest['participant'],'metadata':m,'session_calibration':cal,'feature_names':FEATURES,
                 'X_raw':raw.tolist(),'X_session_calibrated':calibrated.tolist()})+'\n')
    with (destination/'dataset.ts').open('w',encoding='utf-8') as f:
        f.write('@problemName MiloGlove\n@timestamps false\n@univariate false\n@classLabel true '+' '.join(classes)+'\n@data\n')
        for a,label in zip(X,labels):f.write(':'.join(','.join(f'{v:.6g}' for v in a[:,j]) for j in range(9))+':'+label+'\n')
    details={'format_version':1,'accepted_clips':n,'excluded':excluded,'classes':classes,'feature_order':FEATURES,
        'full_shape':list(X.shape),'action_shape':[n,150,9],'sample_hz':50,'hardware_profile':PROFILE,
        'units':{'ax_ay_az':'m/s^2','gx_gy_gz':'rad/s','raw_flex':'ADC counts'},
        'session_roles':session_roles,'normalisation':'Per-wear calibration only. No population scaler was fitted.',
        'action_window_note':'1-4 seconds is cue-aligned, not annotated movement boundaries. Full 6-second clips remain authoritative.',
        'split_note':'All frames/windows from a clip and preferably a wear session must remain in the same split. Unassigned sessions are not silently randomly split.'}
    (destination/'dataset_manifest.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
    (destination/'labels.txt').write_text('\n'.join(labels.tolist()),encoding='utf-8')
    return details

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sessions',nargs='+',type=Path);p.add_argument('--output',type=Path,default=Path('training_export'))
    a=p.parse_args();result=export_dataset(a.sessions,a.output);print(json.dumps(result,indent=2))
