"""Build an offline waveform reviewer and apply human onset/release/end annotations."""
import argparse,json,zipfile
from pathlib import Path
from dataset_tools import load_rows,calibrate,FEATURES,FINGERS,export_dataset

def build_review(folder):
    cal=json.loads((folder/'calibration.json').read_text())
    records=[]
    for p in sorted((folder/'clips').glob('*.json')):
        m=json.loads(p.read_text())
        if m['kind']!='gesture':continue
        rows=load_rows(p.with_suffix('.csv'))
        matrix=calibrate([[r[k] for k in FEATURES] for r in rows],cal) if rows else []
        records.append({'meta':m,'points':[[r['elapsed_ms']/1000,*[round(float(v),4) for v in values]] for r,values in zip(rows,matrix)]})
    source=Path(__file__).with_name('review_template.html').read_text(encoding='utf-8-sig')
    (folder/'review.html').write_text(source.replace('__CLIP_DATA__',json.dumps(records).replace('</',r'<\/')),encoding='utf-8')

def apply_annotations(folder,path):
    records=json.loads(path.read_text(encoding='utf-8-sig'))
    for row in records:
        clip_id=row['clip_id']
        if any(c not in '0123456789abcdef_' for c in clip_id):raise ValueError('Invalid clip ID')
        meta=folder/'clips'/(clip_id+'.json')
        if not meta.is_file():raise ValueError('Unknown clip: '+clip_id)
        m=json.loads(meta.read_text())
        annotations=row['annotations']
        for key in ['action_onset_ms','release_ms','action_end_ms']:
            value=annotations.get(key)
            if value is not None and (type(value) is not int or not 0<=value<=m['duration_ms']):raise ValueError('Invalid annotation time')
        onset=annotations.get('action_onset_ms');end=annotations.get('action_end_ms');release=annotations.get('release_ms')
        if onset is not None and end is not None and onset>=end:raise ValueError('Onset must precede end')
        if release is not None and ((onset is not None and release<onset) or (end is not None and release>end)):
            raise ValueError('Release must be inside the annotated gesture')
        m['annotations']={**annotations,'source':'human_waveform_review'}
        m['signal_reviewed']=bool(row.get('signal_reviewed'))
        # Hard-quality failures remain ineligible regardless of checkbox state.
        m['accepted']=bool(row.get('accepted')) and m['quality']['usable']
        meta.write_text(json.dumps(m,indent=2),encoding='utf-8')
    details=export_dataset([folder],folder/'export');build_review(folder)
    manifest=json.loads((folder/'session.json').read_text())
    manifest['training_export_clips']=details['accepted_clips']
    (folder/'session.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with zipfile.ZipFile(folder.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file():z.write(f,f.relative_to(folder))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('session',type=Path);p.add_argument('--annotations',type=Path)
    a=p.parse_args()
    if a.annotations:apply_annotations(a.session,a.annotations)
    else:build_review(a.session)
    print('Reviewer:',a.session/'review.html')
