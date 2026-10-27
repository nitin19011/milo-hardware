"""Weak-label first prototype. Event-group holdout within one session is NOT independent-session validation."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from features import FEATURE_NAMES, STEP, WINDOW, activity, features

ROOT = Path(__file__).resolve().parents[1]


def main(source, review):
    with zipfile.ZipFile(source) as z:
        metadata = json.loads(z.read("session.json"))
        events = json.loads(z.read("events.json"))
        rows = list(csv.DictReader(io.StringIO(z.read("stream.csv").decode())))
    exclude = set(json.loads(Path(review).read_text())["review_event_ids"])
    gestures = [e for e in events if e["accepted"] and e["kind"] == "gesture" and e["id"] not in exclude]
    negatives = [e for e in events if e["accepted"] and e["kind"] == "background"]
    group = {}
    rng = np.random.default_rng(25023)
    for label in sorted({e["label"] for e in gestures}):
        items = [e for e in gestures if e["label"] == label]
        ids = rng.permutation(len(items)); n = len(items)
        for i, index in enumerate(ids):
            group[items[index]["id"]] = "fit" if i < int(n*.6) else "calibration" if i < int(n*.8) else "test"
    columns = ("ax", "ay", "az", "gx", "gy", "gz", "thumb", "index", "middle", "raw_thumb", "raw_index", "raw_middle")
    windows, info = [], []
    for boot in dict.fromkeys(r["boot_id"] for r in rows):
        segment = [r for r in rows if r["boot_id"] == boot]
        segment = sorted({int(r["seq"]): r for r in segment}.values(), key=lambda r: int(r["seq"]))
        a = np.array([[float(r[k]) for k in columns] for r in segment], dtype=np.float32)
        seq = np.array([int(r["seq"]) for r in segment]); t = np.array([int(r["device_us"]) for r in segment], dtype=np.int64)
        bad = np.array([int(r["imu_ok"]) != 1 or int(r["imu_clipped"]) or int(r["flex_rail_mask"]) for r in segment])
        for end in range(WINDOW-1, len(segment)):
            if seq[end] % STEP: continue
            begin = end-WINDOW+1
            if bad[begin:end+1].any() or (np.diff(seq[begin:end+1]) != 1).any() or (np.diff(t[begin:end+1]) > 40000).any(): continue
            x = features(a[begin:end+1]); row = {"boot": boot, "start_us": int(t[begin]), "end_us": int(t[end]), "label": -1, "split": "unlabelled", "event_id": "", "class": ""}
            for e in gestures:
                if e["start"]["boot_id"] == boot and t[begin] >= e["start"]["device_us_estimate"] and t[end] <= e["end"]["device_us_estimate"]:
                    row.update(label=1, split=group[e["id"]], event_id=e["id"], **{"class": e["label"]}); break
            if row["label"] < 0:
                for e in negatives:
                    if e["start"]["boot_id"] != boot or e["end"]["boot_id"] != boot: continue
                    first, last = e["start"]["device_us_estimate"], e["end"]["device_us_estimate"]
                    if first <= t[begin] and t[end] <= last:
                        # Contiguous negative blocks, with a full-window guard at split boundaries.
                        cut1, cut2 = first + int((last-first)*.6), first + int((last-first)*.8)
                        split = "fit" if t[end] < cut1 else "calibration" if t[begin] > cut1+800000 and t[end] < cut2 else "test" if t[begin] > cut2+800000 else "unlabelled"
                        if split != "unlabelled": row.update(label=0, split=split, event_id=e["id"], **{"class": "background"})
                        break
            windows.append(x); info.append(row)
    X = np.array(windows, dtype=np.float32)
    y = np.array([r["label"] for r in info]); split = np.array([r["split"] for r in info]); act = activity(X)
    fit = list(np.where((split=="fit") & (y==0))[0])
    # Coarse brackets include preparation/rest. Learn from their most active windows.
    for e in gestures:
        if group[e["id"]] != "fit": continue
        ids = np.array([i for i, r in enumerate(info) if r["event_id"] == e["id"]], dtype=int)
        fit.extend(ids[np.argsort(act[ids])[-5:]].tolist())
    fit = np.array(fit)
    def evaluate(scores, which, threshold):
        eligible = [e for e in gestures if group[e["id"]] == which]
        hits = []
        for e in eligible:
            ids = np.array([i for i, r in enumerate(info) if r["event_id"] == e["id"]], dtype=int)
            max_score = float(scores[ids].max()) if len(ids) else 0.
            hits.append({"id": e["id"], "class": e["label"], "max_score": max_score, "hit": bool(max_score>=threshold)})
        ids = np.where((split==which) & (y==0))[0]
        proposals, last = 0, None
        # A proposal can repeat every second during sustained activity, rather than waiting for stillness.
        for i in ids:
            t = info[i]["end_us"]
            if scores[i] >= threshold and (last is None or t-last >= 1_000_000): proposals += 1; last=t
        seconds = float(len(ids)*.1)
        return {"event_brackets": len(hits), "brackets_hit": sum(h["hit"] for h in hits),
                "bracket_hit_rate": sum(h["hit"] for h in hits)/len(hits), "event_results": hits,
                "background_valid_window_seconds": round(seconds, 2), "false_candidate_proposals": proposals,
                "false_proposals_per_minute": proposals*60/seconds, "negative_windows_above_threshold_fraction": float(np.mean(scores[ids]>=threshold))}
    comparisons, models = [], []
    for name, nfeatures in [("imu_binary",39), ("imu_binary_raw_motion",45)]:
        model = RandomForestClassifier(n_estimators=24, max_depth=5, min_samples_leaf=4, class_weight="balanced_subsample", random_state=25023, n_jobs=1)
        model.fit(X[fit, :nfeatures], y[fit]); scores = model.predict_proba(X[:, :nfeatures])[:, 1]
        maxima = [max(scores[i] for i,r in enumerate(info) if r["event_id"]==e["id"]) for e in gestures if group[e["id"]]=="calibration"]
        threshold = max(.01, float(min(maxima))*.75)
        validation = evaluate(scores, "calibration", threshold)
        comparisons.append({"name": name, "nfeatures": nfeatures, "threshold": threshold, "calibration": validation})
        models.append((model, scores))
    best = min(range(len(comparisons)), key=lambda i: comparisons[i]["calibration"]["false_proposals_per_minute"])
    selected = comparisons[best]; model, scores = models[best]
    test = evaluate(scores, "test", selected["threshold"])
    exported = []
    for estimator in model.estimators_:
        tree=estimator.tree_; nodes=[]
        for i in range(tree.node_count):
            values=tree.value[i][0]; positive=float(values[1]/values.sum())
            nodes.append({"left":int(tree.children_left[i]),"right":int(tree.children_right[i]),"feature":int(tree.feature[i]),"threshold":float(np.float32(tree.threshold[i])),"score":positive})
        exported.append(nodes)
    artifact={"model_id":"milo-candidate-rf-v1-20261025","kind":"binary candidate detector, not final gesture recognition",
              "window_samples":40,"sample_hz":50,"stride_samples":5,"feature_names":FEATURE_NAMES[:selected["nfeatures"]],
              "raw_motion_features_used":selected["nfeatures"]==45,"threshold":0.1,"threshold_note":"Permissive development setting chosen after examining same-session results; requires new-session validation.","trees":exported,
              "calibration_id":metadata["calibration_id"],"training_source_sha256":hashlib.sha256(Path(source).read_bytes()).hexdigest()}
    report={"source_session":metadata["session_id"],"input_accepted_gestures":sum(e["accepted"] and e["kind"]=="gesture" for e in events),
            "held_aside_uncertain_ids":sorted(exclude),"provisionally_used_gestures":len(gestures),"positive_event_split":dict((s,sum(v==s for v in group.values())) for s in ("fit","calibration","test")),
            "fit_windows":len(fit),"fit_positive_windows":int((y[fit]==1).sum()),"fit_negative_windows":int((y[fit]==0).sum()),
            "selection":"Variant selected on calibration false proposals; threshold=75% of weakest calibration bracket maximum, not tuned on test.",
            "comparisons":comparisons,"selected_variant":selected["name"],"selected_threshold":selected["threshold"],"same_session_test":test,
            "limits":["Single recording session only; no independent-session generalization test.","Operator brackets are weak labels; hit rate is not physical gesture recall or complete 3-second clip coverage.","Nine uncertain labels excluded, not treated as negatives.","Top-five active windows per fitting gesture selected to reduce preparation/rest label noise.","False proposals measured as repeated proposals at most once/second; later mic upload deduplication/capacity remains separate.","No claim of 99% recall; lower confidence bounds require more representative independent trials."]}
    report['initial_selective_setting']={'threshold':selected['threshold'],'same_session_bracket_hits':test['brackets_hit'],'same_session_brackets':test['event_brackets']}
    report['selection']='Variant selected using calibration of the initial selective setting. Deployed threshold changed to 0.10 after reviewing same-session results; no final held-out test claim.'
    report['selected_threshold']=0.1
    report['threshold_selection_after_inspecting_same_session_results']=True
    report['permissive_same_session_development_check']={which:{'bracket_hits':ev['brackets_hit'],'brackets':ev['event_brackets'],'false_proposals':ev['false_candidate_proposals'],'background_valid_seconds':ev['background_valid_window_seconds'],'false_proposals_per_minute':ev['false_proposals_per_minute']} for which in ('calibration','test') for ev in [evaluate(scores,which,0.1)]}
    report['limits'].append('The permissive threshold was selected after reviewing same-session results. The previous test partition is now development data, not a final held-out test.')
    report['initial_selective_same_session_test']=report.pop('same_session_test')
    (ROOT/'model.json').write_text(json.dumps(artifact,indent=2)+'\n')
    (ROOT/'training_report.json').write_text(json.dumps(report,indent=2)+'\n')
    with (ROOT/'window_scores.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=(*info[0].keys(),"score"));writer.writeheader()
        writer.writerows({**r,"score":float(score)} for r,score in zip(info,scores))
    np.savez_compressed(ROOT/'training_windows.npz',X=X,y=y,split=split,event_id=np.array([r['event_id'] for r in info]),score=scores)
    print(json.dumps({"selected":selected['name'],"threshold":0.1,"initial_selective_threshold":selected['threshold'],"splits":report['positive_event_split'],
        "initial_selective_calibration_hit":f"{selected['calibration']['brackets_hit']}/{selected['calibration']['event_brackets']}",
        "initial_selective_calibration_false_proposals_per_minute":selected['calibration']['false_proposals_per_minute'],
        "initial_selective_test_hit":f"{test['brackets_hit']}/{test['event_brackets']}","initial_selective_test_false_proposals_per_minute":test['false_proposals_per_minute'],"permissive_development_checks":report['permissive_same_session_development_check']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('review');a=p.parse_args();main(a.source,a.review)

