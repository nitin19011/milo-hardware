from pathlib import Path
import zipfile,json,csv,io,hashlib,numpy as np
OUT=Path('outputs/Milo_AI_Background_Negatives_20261025')
if OUT.exists():raise RuntimeError('Preserve existing export; choose a new folder.')
OUT.mkdir()
features=['ax','ay','az','gx','gy','gz','thumb','index','middle']
sources=[('everyday_10min',Path('outputs/Milo_Candidate_Detector_Collection/datasets/Milo_Candidate_Data_20261025_130244_433d4f0c.zip')),
 ('hard_negative_2min',Path('outputs/Milo_Candidate_Detector_v1_20261025/datasets/Milo_Candidate_Data_20261025_182032_a0f92606.zip'))]
X=[];offsets=[];ids=[];groups=[];manifest=[];records=[];rejected=[];source_hashes={}
for tag,path in sources:
 source_hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
 with zipfile.ZipFile(path) as z:
  meta=json.loads(z.read('session.json'));events=json.loads(z.read('events.json'));rows=list(csv.DictReader(io.StringIO(z.read('stream.csv').decode('utf-8-sig'))))
 for event in events:
  if event['kind']!='background' or not event['accepted']:continue
  if event['start']['boot_id']!=event['end']['boot_id']:raise RuntimeError('This export expects a single-boot negative interval.')
  boot=event['start']['boot_id'];start=event['start']['device_us_estimate'];end=event['end']['device_us_estimate']
  for e in events:
   if e['kind']=='gesture' and e['accepted'] and e['start']['boot_id']==boot:
    assert e['end']['device_us_estimate']<start or e['start']['device_us_estimate']>end
  chosen=[r for r in rows if r['boot_id']==boot and start<=int(r['device_us'])<=end]
  chosen=sorted({int(r['seq']):r for r in chosen}.values(),key=lambda r:int(r['seq']))
  folder=OUT/'continuous'/tag;folder.mkdir(parents=True)
  cols=['source_seq','device_us','elapsed_s',*features,'label']
  with (folder/'model_features.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.writer(f);w.writerow(cols)
   for row in chosen:w.writerow([row['seq'],row['device_us'],(int(row['device_us'])-start)/1e6,*[row[k] for k in features],'background'])
  with (folder/'diagnostics.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=chosen[0].keys());w.writeheader();w.writerows(chosen)
  lookup={int(r['seq']):r for r in chosen};first=min(lookup);last=max(lookup);potential=(last-first+1)//150;n_good=0
  for k in range(potential):
   first_seq=first+k*150;window=[lookup.get(i) for i in range(first_seq,first_seq+150)]
   reason=[]
   if any(r is None for r in window):reason.append('missing_sample')
   else:
    a=np.array([[float(r[c]) for c in features] for r in window],dtype=np.float32);t=np.array([int(r['device_us']) for r in window],dtype=np.int64)
    if not np.isfinite(a).all():reason.append('nonfinite')
    if not np.isin(a[:,6:],[0,1]).all():reason.append('nonbinary_finger')
    if any(int(r['imu_ok'])!=1 or int(r['imu_clipped']) or int(r['flex_rail_mask']) for r in window):reason.append('sensor_fault')
    if not ((np.diff(t)>0)&(np.diff(t)<=40000)).all():reason.append('irregular_acquisition')
    if int(window[-1]['queue_drops_total'])!=int(window[0]['queue_drops_total']):reason.append('queue_drop')
   clipid=f'{tag}_{k+1:04d}'
   if reason:
    rejected.append({'id':clipid,'source':tag,'first_seq':first_seq,'reasons':reason});continue
   rel=Path('clips')/'background'/(clipid+'.csv');target=OUT/rel;target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(features);w.writerows(a.tolist())
   entry={'sample_id':clipid,'label':'background','source_recording':tag,'source_session':meta['session_id'],'participant':meta['participant'],'source_event_id':event['id'],'boot_id':boot,'first_seq':first_seq,'last_seq':first_seq+149,'first_device_us':int(t[0]),'last_device_us':int(t[-1]),'sample_rate_hz':50,'duration_ms':3000,'sample_count':150,'calibration_id':meta['calibration_id'],'csv_path':rel.as_posix(),'valid':True}
   target.with_suffix('.json').write_text(json.dumps(entry,indent=2)+'\n',encoding='utf-8')
   X.append(a);offsets.append(t-t[0]);ids.append(clipid);groups.append(tag);manifest.append(entry);n_good+=1
  info={'source_recording':tag,'original_zip':path.name,'original_zip_sha256':source_hashes[path],'original_session_role':meta['split_role'],'event_id':event['id'],'label':'background','labelled_duration_s':event['duration_s'],'continuous_frames':len(chosen),'unique_missing_samples':last-first+1-len(chosen),'potential_nonoverlapping_3s_windows':potential,'exported_3s_windows':n_good,'excluded_3s_windows':potential-n_good,'calibration_id':meta['calibration_id'],'source_bracket':event,'prior_use':'Already used for glove candidate-detector development; not an untouched end-to-end test set.'}
  (folder/'metadata.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8');records.append(info)
X=np.stack(X).astype(np.float32)
np.savez_compressed(OUT/'background_3s.npz',X=X,y=np.array(['background']*len(X)),feature_names=np.array(features),sample_id=np.array(ids),recording_group=np.array(groups),sample_offsets_us=np.stack(offsets),is_command=np.zeros(len(X),dtype=np.uint8))
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=manifest[0].keys());w.writeheader();w.writerows(manifest)
(OUT/'excluded_windows.json').write_text(json.dumps(rejected,indent=2)+'\n',encoding='utf-8')
summary={'label':'background','feature_names':features,'sample_rate_hz':50,'model_array_shape':list(X.shape),'total_labelled_seconds':sum(r['labelled_duration_s'] for r in records),'total_continuous_frames':sum(r['continuous_frames'] for r in records),'exported_windows':len(X),'exported_window_seconds':len(X)*3,'excluded_windows':len(rejected),'numeric_multiclass_id_assumed':False,'units':{'accel':'m/s^2 including gravity','gyro':'rad/s; bias not subtracted','fingers':'0=NOT_BENT,1=BENT'},'sources':records,'source_files_modified':False}
(OUT/'dataset_info.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
(OUT/'README_AI.txt').write_text('''MILO - BACKGROUND / NO-COMMAND NEGATIVE DATA
25 October 2026

ONLY explicitly accepted mixed_everyday intervals were extracted. The original
first ZIP also contains positive command gestures; those are NOT in this export.
Two labelled recordings: about 10 minutes + about 2 minutes, same wearer Nitin.

MODEL INPUT FEATURES (9, exact order):
ax, ay, az, gx, gy, gz, thumb, index, middle
Acceleration: m/s^2, gravity included. Gyro: rad/s, bias NOT subtracted.
Fingers: exactly 0 NOT_BENT / 1 BENT; all three fingers active.
Raw ADC and prior detector scores appear only in diagnostics, NOT model tensors.

FILES
continuous/<recording>/model_features.csv: full labelled interval, with sequence
and device-time columns. Select ONLY the nine named features as model inputs.
continuous/<recording>/diagnostics.csv: original diagnostic columns, sorted by
source sequence. No missing values were synthesized. Missing sequence positions
are gaps, not zeros. Reordered received packets were placed in source order.
clips/background/: valid non-overlapping 3-second CSVs, exactly 150 rows x9.
background_3s.npz: X shape (N,150,9), y string labels 'background', recording_group,
feature_names, sample_id, sample_offsets_us and binary is_command=0.
manifest.csv: per-clip provenance. dataset_info.json: counts and recording bounds.
excluded_windows.json: windows rejected for gaps/health/timing problems.

LABEL MAPPING
No numeric multiclass ID is imposed. Add 'background' / 'no_command' to your own
class mapping. Do not assume zero is the multiclass background ID: an existing
positive dataset may use zero for Come. is_command=0 is explicitly binary only.

PREPROCESSING
X is RAW PHYSICAL IMU plus BINARY fingers. Existing positive collection exports
may have gyro-bias-corrected X and uncorrected X_raw: use X_raw for a direct match,
or apply the same intended bias correction consistently to both datasets.
No normalization/resampling/interpolation was applied. Do not normalize binary
states as continuous flex angles. Timestamps/diagnostics are not model features.
Calibration ID: nitin-20261023-usb-relaxed-fist-v3. Earlier positive datasets can
use different thresholds or disabled fingers: check their metadata when combining.

DATA SPLITS
Preserve recording groups; avoid random splits of neighbouring/overlapping
windows across train/test. Keep a genuinely separate recording for final testing.
Both recordings have been used for local glove-trigger development. They are
not an untouched test of the complete system, and do not establish 99% recall.
Unlabelled portions and uncertain positive actions were not relabelled negative.

LOAD
import numpy as np
z=np.load('background_3s.npz', allow_pickle=False)
X=z['X']                       # (N,150,9)
y=z['y']                       # string 'background'
groups=z['recording_group']
# If your model requires channels first: X.transpose(0,2,1)
''',encoding='utf-8')
assert X.shape[1:]==(150,9) and np.isin(X[:,:,6:],[0,1]).all() and np.isfinite(X).all()
loaded=np.load(OUT/'background_3s.npz',allow_pickle=False);assert np.array_equal(loaded['X'],X)
for entry in manifest:
 data=np.loadtxt(OUT/entry['csv_path'],delimiter=',',skiprows=1,dtype=np.float32);assert data.shape==(150,9)
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in source_hashes.items())
files=sorted(p for p in OUT.rglob('*') if p.is_file());hashes={p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(OUT/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8');files.append(OUT/'SHA256SUMS.json')
archive=OUT.with_suffix('.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in files:z.write(p,Path(OUT.name)/p.relative_to(OUT))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for rel,sha in hashes.items():assert hashlib.sha256(z.read(OUT.name+'/'+rel)).hexdigest()==sha
print(json.dumps({'zip':str(archive.resolve()),'zip_mb':round(archive.stat().st_size/1e6,2),'continuous_frames':summary['total_continuous_frames'],'labelled_seconds':summary['total_labelled_seconds'],'X_shape':list(X.shape),'excluded_windows':len(rejected),'windows_per_recording':{r['source_recording']:r['exported_3s_windows'] for r in records},'source_files_unchanged':True,'validation':'passed'},indent=2))
