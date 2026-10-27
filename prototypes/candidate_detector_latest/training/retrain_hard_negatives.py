"""Add explicitly labelled hard negatives; preserve uncertain positives as unlabelled."""
from pathlib import Path
import csv,io,json,zipfile,hashlib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from features import features, activity, FEATURE_NAMES

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]
V1=ROOT.parent/'Milo_Candidate_Detector_v1_20261025'
HARD=V1/'datasets/Milo_Candidate_Data_20261025_182032_a0f92606.zip'


def proposal_rate(scores,info,ids,threshold):
    last={};count=0;above=0
    for i in ids:
        key=info[i]['source']+'|'+info[i]['boot'];t=info[i]['end_us']
        if scores[i]>=threshold:
            above+=1
            if key not in last or t-last[key]>=1_000_000:last[key]=t;count+=1
    seconds=len(ids)*.1
    return {'valid_seconds':round(seconds,2),'proposals':count,'proposals_per_minute':count*60/seconds,'window_fraction_above':above/len(ids)}


def main(v1_folder=V1, hard_negative_zip=HARD):
    global V1,HARD
    V1=Path(v1_folder);HARD=Path(hard_negative_zip)
    old=np.load(V1/'training_windows.npz');X=list(old['X']);y=list(old['y']);split=list(old['split'])
    info=list(csv.DictReader((V1/'window_scores.csv').open()))
    for r in info:r['source']='original';r['end_us']=int(r['end_us']);r['start_us']=int(r['start_us'])
    with zipfile.ZipFile(HARD) as z:
        meta=json.loads(z.read('session.json'));events=json.loads(z.read('events.json'))
        rows=list(csv.DictReader(io.StringIO(z.read('stream.csv').decode())))
    negative=next(e for e in events if e['accepted'] and e['kind']=='background')
    boot=negative['start']['boot_id'];first=negative['start']['device_us_estimate'];last=negative['end']['device_us_estimate']
    rows=sorted({int(r['seq']):r for r in rows if r['boot_id']==boot}.values(),key=lambda r:int(r['seq']))
    a=np.array([[float(r[k]) for k in ['ax','ay','az','gx','gy','gz','thumb','index','middle','raw_thumb','raw_index','raw_middle']] for r in rows],dtype=np.float32)
    seq=np.array([int(r['seq']) for r in rows]);t=np.array([int(r['device_us']) for r in rows]);bad=np.array([int(r['imu_ok'])!=1 or int(r['imu_clipped']) or int(r['flex_rail_mask']) for r in rows])
    cut1=first+int((last-first)*.6);cut2=first+int((last-first)*.8)
    for end in range(39,len(a)):
        begin=end-39
        if seq[end]%5 or t[begin]<first or t[end]>last:continue
        if bad[begin:end+1].any() or (np.diff(seq[begin:end+1])!=1).any() or (np.diff(t[begin:end+1])>40000).any():continue
        part='fit' if t[end]<cut1 else 'calibration' if t[begin]>cut1+800000 and t[end]<cut2 else 'test' if t[begin]>cut2+800000 else 'unlabelled'
        X.append(features(a[begin:end+1]));y.append(0 if part!='unlabelled' else -1);split.append(part)
        info.append({'source':'hard_negative','boot':boot,'start_us':int(t[begin]),'end_us':int(t[end]),'label':0 if part!='unlabelled' else -1,'split':part,'event_id':negative['id'],'class':'background'})
    X=np.asarray(X,dtype=np.float32);y=np.asarray(y,dtype=int);split=np.asarray(split);source=np.array([r['source'] for r in info]);act=activity(X)
    fit=list(np.where((y==0)&(split=='fit'))[0])
    positive_ids=sorted({r['event_id'] for r in info if r['source']=='original' and int(r['label'])==1})
    for eid in positive_ids:
        ids=np.array([i for i,r in enumerate(info) if r['event_id']==eid and r['split']=='fit'],dtype=int)
        if len(ids):fit.extend(ids[np.argsort(act[ids])[-5:]].tolist())
    fit=np.array(fit);weights=np.where((source[fit]=='hard_negative')&(y[fit]==0),4.,1.)
    dev_events=[]
    for eid in positive_ids:
        ids=np.array([i for i,r in enumerate(info) if r['event_id']==eid],dtype=int)
        if info[ids[0]]['split']!='fit':dev_events.append((eid,info[ids[0]]['class'],ids))
    comparisons=[];models=[]
    for family in ['forest','extra']:
        for depth in [5,7]:
            for nf in [39,45]:
                cls=RandomForestClassifier if family=='forest' else ExtraTreesClassifier
                model=cls(n_estimators=32,max_depth=depth,min_samples_leaf=3,class_weight='balanced_subsample' if family=='forest' else 'balanced',random_state=25025,n_jobs=1)
                model.fit(X[fit,:nf],y[fit],sample_weight=weights);scores=model.predict_proba(X[:,:nf])[:,1]
                # All 54 non-fitting original brackets are explicitly DEVELOPMENT labels now.
                maxima=[float(scores[ids].max()) for _,_,ids in dev_events]
                threshold=max(.015,min(maxima)*.5)
                cal={s:proposal_rate(scores,info,np.where((source==s)&(split=='calibration')&(y==0))[0],threshold) for s in ['original','hard_negative']}
                entry={'name':f'{family}_depth{depth}_features{nf}','nfeatures':nf,'threshold':threshold,'development_brackets':len(dev_events),'development_hits':sum(x>=threshold for x in maxima),'calibration_background':cal,'worst_calibration_proposals_per_minute':max(x['proposals_per_minute'] for x in cal.values()),'nodes':sum(e.tree_.node_count for e in model.estimators_)}
                comparisons.append(entry);models.append((model,scores))
    best=min(range(len(comparisons)),key=lambda i:(comparisons[i]['worst_calibration_proposals_per_minute'],sum(v['proposals_per_minute'] for v in comparisons[i]['calibration_background'].values()),comparisons[i]['nodes']))
    selected=comparisons[best];model,scores=models[best];threshold=selected['threshold']
    tests={s:proposal_rate(scores,info,np.where((source==s)&(split=='test')&(y==0))[0],threshold) for s in ['original','hard_negative']}
    old_model=json.loads((V1/'model.json').read_text())
    def old_predict(x):
        total=0.
        for tree in old_model['trees']:
            n=0
            while tree[n]['feature']>=0:
                v=tree[n];n=v['left'] if x[v['feature']]<=v['threshold'] else v['right']
            total+=tree[n]['score']
        return total/len(old_model['trees'])
    hard_test=np.where((source=='hard_negative')&(split=='test')&(y==0))[0]
    previous=np.zeros(len(X));previous[hard_test]=[old_predict(X[i]) for i in hard_test]
    old_test=proposal_rate(previous,info,hard_test,.1)
    trees=[]
    for estimator in model.estimators_:
        t=estimator.tree_;nodes=[]
        for i in range(t.node_count):
            v=t.value[i][0];nodes.append({'left':int(t.children_left[i]),'right':int(t.children_right[i]),'feature':int(t.feature[i]),'threshold':float(np.float32(t.threshold[i])),'score':float(v[1]/v.sum())})
        trees.append(nodes)
    artifact={'model_id':'milo-candidate-rf-v2-hardneg-20261025','kind':'binary candidate detector; not final action recognition','window_samples':40,'sample_hz':50,'stride_samples':5,'feature_names':FEATURE_NAMES[:selected['nfeatures']],'raw_motion_features_used':selected['nfeatures']==45,'threshold':threshold,'trees':trees,'calibration_id':meta['calibration_id'],'hard_negative_source_sha256':hashlib.sha256(HARD.read_bytes()).hexdigest()}
    report={'selected':selected,'comparisons':comparisons,'negative_time_block_checks':tests,'previous_model_same_hard_negative_test_block':old_test,'hard_negative_label_seconds':negative['duration_s'],'fit_original_gesture_brackets':len(positive_ids)-len(dev_events),'development_positive_brackets':len(dev_events),'positive_fitting_windows':int((y[fit]==1).sum()),'fitting_negative_windows':int((y[fit]==0).sum()),'uncertain_original_brackets_used':False,'new_positive_independent_session_present':False,'limits':['Only 23 seconds of this hard-negative recording remain in the final time-block check.','All original non-fitting positive brackets now serve model development; hit rate is not an independent recall estimate.','More background training can trade off new unseen positive gestures; live validation is necessary.','Overlapping proposals are still retained. Grouping in the UI does not conceal the raw window count.']}
    (ROOT/'model.json').write_text(json.dumps(artifact,indent=2)+'\n');(ROOT/'training_report.json').write_text(json.dumps(report,indent=2)+'\n')
    np.savez_compressed(ROOT/'training_windows.npz',X=X,y=y,split=split,source=source,score=scores)
    with (ROOT/'window_scores.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['source','boot','start_us','end_us','label','split','event_id','class','score']);writer.writeheader()
        writer.writerows({k:r[k] for k in ['source','boot','start_us','end_us','label','split','event_id','class']}|{'score':float(s)} for r,s in zip(info,scores))
    print(json.dumps({'selected':selected,'negative_checks':tests,'previous_model_same_new_background_test_block':old_test},indent=2))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--v1-folder',type=Path,default=V1)
    p.add_argument('--hard-negative-zip',type=Path,default=HARD)
    a=p.parse_args();main(a.v1_folder,a.hard_negative_zip)
