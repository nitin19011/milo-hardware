"""Data schema, quality checks, calibration and portable training exports."""
import argparse,csv,json,math,zipfile
from pathlib import Path
import numpy as np
PROFILE='mpu6050_16g_2000dps_21hz_50hz_binary_flex_v5'
FEATURES=['ax','ay','az','gx','gy','gz','thumb','index','middle']
FINGERS=['thumb','index','middle']
COLUMNS=['seq','timestamp_us','elapsed_ms','boot_id',*FEATURES,'imu_valid','flex_rail_mask','imu_errors','queue_dropped',
         'raw_ax','raw_ay','raw_az','raw_gx','raw_gy','raw_gz','rssi_dbm']

def flatten(data):
    if data.get('type')!='hand_sample' or data.get('hardware_profile')!=PROFILE:
        raise ValueError('Upload the updated MBF_v1 collection firmware first (all three flex sensors; motor stays off).')
    row={k:data[k] for k in ['seq','timestamp_us','boot_id','rssi_dbm']}
    row.update({k:data['imu'][k] for k in FEATURES[:6]})
    states=data['flex']
    if any(states[k] not in ('BENT','NOT_BENT') for k in FINGERS):raise ValueError('Uncalibrated or invalid finger state; upload final binary firmware.')
    row.update({k:int(states[k]=='BENT') for k in FINGERS})
    row.update({'imu_valid':bool(data['imu']['valid']),**data['quality'],
                'elapsed_ms':data['collection']['elapsed_ms']})
    for name,value in zip(['raw_ax','raw_ay','raw_az','raw_gx','raw_gy','raw_gz'],data['imu_raw']):row[name]=value
    for k in FEATURES:
        if not isinstance(row[k],(int,float)) or not math.isfinite(row[k]):raise ValueError('Non-finite sensor reading')
    if any(type(row[k]) is not int or row[k] not in (0,1) for k in FINGERS):raise ValueError('Invalid binary finger state')
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
    rail=sum((r['flex_rail_mask'] & 7)!=0 for r in rows)
    clipping=sum(any(abs(r['raw_'+k])>=32700 for k in FEATURES[:6]) for r in rows)
    if invalid:hard.append('imu_read_failure')
    if rail:hard.append('flex_adc_rail')
    if clipping:hard.append('imu_range_clipping')
    if rows[-1]['queue_dropped']!=rows[0]['queue_dropped']:hard.append('queue_drops')
    return {'usable':not hard,'errors':hard,'warnings':notes,'n':len(rows),'imu_invalid':invalid,
            'rail_samples':rail,'clipped_samples':clipping,'first_ms':int(elapsed[0]),'last_ms':int(elapsed[-1])}

def calibrate(matrix,cal):
    a=np.asarray(matrix,dtype=np.float32).copy()
    if a.ndim!=2 or a.shape[1]!=len(FEATURES):raise ValueError('Expected exactly nine features: IMU six axes, thumb, index and middle.')
    for i,k in enumerate(FEATURES[3:6],3):a[:,i]-=cal['gyro_bias_rad_s'][k]
    if not np.isin(a[:,6:],[0,1]).all():raise ValueError('Finger features must be binary 0/1, never ADC values.')
    return a

def release_candidate(rows,cal,start_ms=1000,end_ms=4500):
    # This is review assistance, never automatically promoted to ground-truth annotation.
    a=calibrate([[r[k] for k in FEATURES] for r in rows],cal)
    # A loose grip may bend only one monitored finger under the current thresholds.
    t=np.array([r['elapsed_ms'] for r in rows]);score=np.mean(a[:,6:],axis=1)
    candidates=[]
    for i in range(5,len(rows)-5):
        if not start_ms<=t[i]<=end_ms:continue
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
    accepted=[];excluded=[];classes=None;session_roles={};definition=None;duration=None;view=None
    for folder in folders:
        manifest=json.loads((folder/'session.json').read_text(encoding='utf-8'))
        current=manifest['class_order']
        if classes is None:classes=current
        if classes!=current:raise ValueError('Different class definitions/orders; review before combining sessions.')
        if definition is None:definition=manifest['definition_sha256']
        if definition!=manifest['definition_sha256']:raise ValueError('Gesture definitions changed between sessions; do not merge silently.')
        cfg=manifest['class_definitions'];clip_ms=manifest['clip_ms']
        current_view=(cfg.get('model_view_start_ms',1000),cfg.get('model_view_end_ms',4000))
        if duration is None:duration=clip_ms;view=current_view
        if duration!=clip_ms or view!=current_view:raise ValueError('Recording lengths or model views differ; do not merge silently.')
        if clip_ms%20 or any(type(v) is not int or v%20 for v in view) or not 0<=view[0]<view[1]<=clip_ms:
            raise ValueError('Invalid recording length or model view.')
        if manifest['hardware_profile']!=PROFILE:raise ValueError('Different sensor profile: start a new three-finger session.')
        cal=json.loads((folder/'calibration.json').read_text())
        session_roles[manifest['session_id']]=manifest.get('split_role','unassigned')
        for meta_path in sorted((folder/'clips').glob('*.json')):
            m=json.loads(meta_path.read_text());
            if m['kind']!='gesture':continue
            if not m.get('accepted') or not m['quality']['usable']:
                excluded.append({'clip_id':m['clip_id'],'quality':m['quality'],'accepted':m.get('accepted')});continue
            if m['quality']['warnings']:
                excluded.append({'clip_id':m['clip_id'],'reason':'repeat_warning_clip_for_clean_training','warnings':m['quality']['warnings']});continue
            rows=load_rows(meta_path.with_suffix('.csv'))
            if m['duration_ms']!=duration:raise ValueError('Clip duration disagrees with its session.')
            q=quality(rows,m['duration_ms'])
            if not q['usable']:excluded.append({'clip_id':m['clip_id'],'quality':q});continue
            time_=np.array([r['elapsed_ms'] for r in rows])
            values=np.array([[r[k] for k in FEATURES] for r in rows],dtype=np.float32)
            grid=np.arange(0,duration,20)
            # At most 19 ms edge hold; no internal losses allowed by the quality gate.
            previous=np.clip(np.searchsorted(time_,grid,side='right')-1,0,len(rows)-1)
            regular=np.column_stack([*[np.interp(grid,time_,values[:,j]) for j in range(6)],values[previous,6:]]).astype(np.float32)
            if not np.isin(regular[:,6:],[0,1]).all():raise ValueError('Non-binary state in export.')
            accepted.append((m,manifest,regular,calibrate(regular,cal),cal))
    if classes is None:raise ValueError('No sessions supplied')
    n=len(accepted)
    X=np.stack([a[2] for a in accepted]) if n else np.empty((0,duration//20,len(FEATURES)),dtype=np.float32)
    Xc=np.stack([a[3] for a in accepted]) if n else np.empty((0,duration//20,len(FEATURES)),dtype=np.float32)
    start,stop=view[0]//20,view[1]//20
    labels=np.array([a[0]['class_id'] for a in accepted],dtype='U40')
    y=np.array([classes.index(v) for v in labels],dtype=np.int64)
    groups=np.array([a[1]['session_id'] for a in accepted],dtype='U40')
    clip_ids=np.array([a[0]['clip_id'] for a in accepted],dtype='U64')
    roles=np.array([a[1].get('split_role','unassigned') for a in accepted],dtype='U16')
    np.save(destination/'X.npy',Xc)
    np.savez_compressed(destination/'dataset.npz',X=Xc,X_channels_first=Xc.transpose(0,2,1),X_raw=X,X_session_calibrated=Xc,
        X_raw_channels_first=X.transpose(0,2,1),X_calibrated_channels_first=Xc.transpose(0,2,1),
        X_action_raw=X[:,start:stop,:],X_action_calibrated=Xc[:,start:stop,:],y=y,labels=labels,
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
        for a,label in zip(X,labels):f.write(':'.join(','.join(f'{v:.6g}' for v in a[:,j]) for j in range(len(FEATURES)))+':'+label+'\n')
    details={'format_version':1,'accepted_clips':n,'excluded':excluded,'classes':classes,'feature_order':FEATURES,
        'full_shape':list(X.shape),'action_shape':[n,stop-start,len(FEATURES)],'clip_ms':duration,'model_view_ms':list(view),'sample_hz':50,'hardware_profile':PROFILE,
        'active_flex_sensors':FINGERS,'disabled_sensors':{},
        'units':{'ax_ay_az':'m/s^2','gx_gy_gz':'rad/s','finger_features':'0=NOT_BENT, 1=BENT'},
        'session_roles':session_roles,'normalisation':'Gyro bias corrected using open-hand fit check. Finger states unchanged; never scaled or linearly interpolated.',
        'state_thresholds':{k:{n:accepted[0][4]['flex_diagnostics'][k][n] for n in ['bend_threshold','release_threshold','bend_increases']} for k in FINGERS} if accepted else {},
        'action_window_note':'Fixed model view uses the same bounds for every class, including background. It is not an annotation of movement boundaries. Full clips remain authoritative.',
        'split_note':'All frames/windows from a clip and preferably a wear session must remain in the same split. Unassigned sessions are not silently randomly split.'}
    (destination/'dataset_manifest.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
    (destination/'labels.txt').write_text('\n'.join(labels.tolist()),encoding='utf-8')
    return details

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sessions',nargs='+',type=Path);p.add_argument('--output',type=Path,default=Path('training_export'))
    a=p.parse_args();result=export_dataset(a.sessions,a.output);print(json.dumps(result,indent=2))


def bend_states(row,cal,previous=None):
    """Reference firmware hysteresis for offline replay; collection uses the transmitted states."""
    result={}
    for k in FINGERS:
        spec=cal['flex_diagnostics'][k];was=(previous or {}).get(k,False)
        threshold=spec['release_threshold'] if was else spec['bend_threshold']
        if was:result[k]=row[k]>threshold if spec['bend_increases'] else row[k]<threshold
        else:result[k]=row[k]>=threshold if spec['bend_increases'] else row[k]<=threshold
    return result

def calibration_report(cal):
    lines=['Milo three-finger calibration','Keep the same resistor and glove fit for collection.',
           'Training uses only 0=NOT_BENT, 1=BENT finger states. Fixed thresholds match firmware.','']
    if cal.get('threshold_revision'):
        lines.extend(['Raw pose summaries below are historical diagnostic references.',cal['threshold_revision'],''])
    for k,d in cal['flex_diagnostics'].items():
        p=d['poses']
        lines.append(f"{k.capitalize()}: open {p['open']['median']:.0f}, fist {p['fist']['median']:.0f}, loose grip {p['ball_grip']['median']:.0f}")
        lines.append(f"  Span {d['span_counts']:.0f}; noise SD open {p['open']['std']:.1f}, fist {p['fist']['std']:.1f}")
        lines.append(f"  Bending {'increases' if d['bend_increases'] else 'decreases'} readings; enter BENT at {d['bend_threshold']}, release at {d['release_threshold']}.")
    return '\n'.join(lines)+'\n'


def verify_pose(rows,pose):
    expected=0 if pose=='open' else 1
    steady=[r for r in rows if r['elapsed_ms']>=500]
    return [k for k in FINGERS if not steady or sum(r[k]==expected for r in steady)/len(steady)<.90]

def throw_release_fingers(rows,lead_ms=1000):
    released=[]
    for k in FINGERS:
        previous=None
        for r in rows:
            if previous==1 and r[k]==0 and r['elapsed_ms']>=lead_ms:
                released.append(k);break
            previous=r[k]
    return released
