"""Incorrect-for-target examples. They are not automatically global background labels."""
import csv
from datetime import datetime
from pathlib import Path
import zipfile
import numpy as np
from collector_core import (ACTIVITIES, FEATURES, Connection, configure_wifi, save_json,
                            Session as BaseSession, CLASSES as VALID_CLASSES)

MISTAKES = {
    "come": [
        ("wrong_finger", "Wrong finger", "Beckon using your middle finger while keeping the index extended."),
        ("outward", "Wrong direction", "Move/curl the index away from yourself rather than beckoning inward."),
        ("whole_hand", "Whole-hand opening", "Open and close the whole hand, without the intended index beckon."),
        ("no_beckon", "Static wrong pose", "Hold a partially curled index still without a beckoning movement."),
        ("incomplete", "Incomplete movement", "Begin the beckon but stop before completing the finger movement."),
    ],
    "sit": [
        ("all_fingers_open", "All fingers extended", "Move the hand down with ALL fingers extended instead of only pointing the index."),
        ("point_up", "Point at the sky", "Point the index upward instead of down."),
        ("point_sideways", "Point sideways", "Point the index horizontally to the side instead of down."),
        ("closed_fist", "Closed fist downward", "Move a closed fist downward; keep the index bent."),
        ("incomplete", "Incomplete downward point", "Begin lowering the hand but stop while the pointing direction is still horizontal."),
    ],
    "paw": [
        ("fist_palm_up", "Palm-up fist", "Present an upward-facing CLOSED fist instead of an open palm."),
        ("palm_down", "Palm faces down", "Present an open hand with the palm facing down."),
        ("palm_vertical", "Palm vertical", "Present an open hand with the palm vertical, not facing upward."),
        ("curled_fingers", "Palm up, curled fingers", "Present the palm upward but curl the index and middle instead of opening them."),
        ("incomplete", "Incomplete palm turn", "Start rotating the palm up but stop before it faces upward."),
    ],
    "spin": [
        ("no_index_point", "Fist rotates clockwise", "Turn a closed fist clockwise without extending the index to point."),
        ("counterclockwise", "Turn counterclockwise", "Point with the index and turn the hand COUNTERCLOCKWISE."),
        ("no_rotation", "Point without turning", "Point horizontally but do not rotate the hand."),
        ("side_to_side", "Side-to-side motion", "Point and move sideways, without a clear clockwise turn."),
        ("incomplete", "Incomplete turn", "Start the turn but stop before making a clear clockwise motion."),
    ],
    "bang": [
        ("thumb_folded", "Thumb folded", "Point the index horizontally but keep the thumb folded instead of forming the gun."),
        ("middle_extended", "Middle also extended", "Extend index, thumb AND middle instead of folding the middle."),
        ("thumb_only", "Thumb only", "Extend only the thumb while the index and middle stay bent."),
        ("index_curled", "Index curled", "Keep the thumb extended but curl the index instead of forming a gun."),
        ("incomplete", "Incomplete gun shape", "Start forming the gun but stop with a partially curled index and folded thumb."),
    ],
    "throw_overhand": [
        ("no_release", "Never release fingers", "Swing overhand while keeping your imaginary-ball grip closed throughout."),
        ("raise_only", "Raise, do not throw", "Raise the hand near the shoulder, then stop without the forward throw."),
        ("sidearm", "Sidearm path", "Use a sideways arm swing instead of the defined overhand path."),
        ("release_too_early", "Release before swinging", "Open the fingers BEFORE starting the swing; don't release during the throw."),
        ("incomplete", "Incomplete swing", "Begin an overhand swing but stop before its forward release/follow-through."),
    ],
    "throw_underhand": [
        ("no_release", "Never release fingers", "Swing underhand while keeping the imaginary-ball grip closed throughout."),
        ("lift_only", "Lift, do not swing", "Lift the hand from the hip without a forward underhand swing."),
        ("sidearm", "Sideways path", "Swing sideways rather than forward from below."),
        ("release_too_early", "Release before swinging", "Open the fingers BEFORE starting the swing; don't release during it."),
        ("incomplete", "Backswing only", "Move the hand backward to prepare, then stop without swinging forward/releasing."),
    ],
}
CLASSES = tuple((key, "Wrong " + title, "Perform an intentionally WRONG version of " + title + ".") for key, title, _ in VALID_CLASSES)
CUSTOM = ("custom", "Custom wrong example", "Perform your own deliberately wrong variant. Add a short note if useful.")


class Session(BaseSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.meta.update(schema="milo-incorrect-gesture-v1", sample_kind="incorrect_attempt",
            sample_semantics="Deliberately wrong for the intended gesture. Not necessarily globally background.",
            intentional_attempt=True, candidate_detector_label="intentional_attempt",
            global_label_scope="Final gesture classifier only; not a negative label for the local candidate detector.",
            classes=[{"intended_gesture":key,"valid_definition":instruction,"mistake_suggestions":MISTAKES[key]} for key, _, instruction in VALID_CLASSES],
            context_policy="Export only the operator bracket; continuous raw stream preserves surrounding data.",
            model_gating=False, fixed_clip_duration=False)
        save_json(self.folder/"session.json", self.meta)

    def start(self, kind, label, now_ns=None, mistake_id=None, mistake_description=None,
              observed_valid_gesture="unknown", note=""):
        if observed_valid_gesture == label:
            raise ValueError("A correct example of the intended gesture is not a wrong attempt. Choose another mistake.")
        if observed_valid_gesture not in {"unknown","no_valid_command",*(c[0] for c in VALID_CLASSES)}:
            raise ValueError("Unknown observed gesture label.")
        if mistake_id is None:
            count=self.snapshot()["counts"].get(label,0)
            plan=MISTAKES[label][(count//4)%5]
            mistake_id,mistake_description=plan[0],plan[2]
        global_label=None if observed_valid_gesture=="unknown" else "background" if observed_valid_gesture=="no_valid_command" else observed_valid_gesture
        annotation={"sample_kind":"incorrect_attempt","dataset_label":"wrong_"+label,
            "intentional_attempt":True,"candidate_detector_label":"intentional_attempt",
            "global_label_scope":"final_gesture_classifier_only",
            "intended_gesture":label,"is_correct_for_intended":False,"mistake_id":mistake_id,
            "mistake_description":mistake_description or "custom wrong attempt","operator_note":note,
            "observed_valid_gesture":observed_valid_gesture,"global_class_label":global_label}
        return super().start("incorrect_attempt",label,now_ns,annotation=annotation)

    def export(self):
        self.close_input()
        accepted=[e for e in self.events if e["kind"]=="incorrect_attempt" and e["accepted"]]
        samples=[];boundaries=[0];entries=[];labels=[];targets=[];other=[];sample_ids=[]
        repetitions={key:0 for key,_,_ in VALID_CLASSES}
        for e in accepted:
            a,b=e["start"]["device_us_estimate"],e["end"]["device_us_estimate"]
            chosen=[f for f in self.frames if f.boot==e["start"]["boot_id"] and a<=f.device_us<=b]
            matrix=np.asarray([f.features for f in chosen],dtype=np.float32)
            if matrix.ndim!=2 or matrix.shape[1]!=9 or not len(matrix):raise ValueError("Unexpected empty/invalid accepted bracket")
            if not np.isfinite(matrix).all() or not np.isin(matrix[:,6:],[0,1]).all():raise ValueError("Invalid model features")
            target=e["intended_gesture"];repetitions[target]+=1
            sample_id=f'wrong_{target}_{repetitions[target]:02d}_{e["id"]}'
            folder=self.folder/"wrong_examples"/target;folder.mkdir(parents=True,exist_ok=True)
            path=folder/(sample_id+".csv")
            with path.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.writer(handle);writer.writerow(FEATURES);writer.writerows(matrix.tolist())
            meta=dict(e);meta.update(sample_id=sample_id,sample_count=len(matrix),sample_hz=50,
                sample_offsets_us=[f.device_us-chosen[0].device_us for f in chosen],
                sensor_span_s=(chosen[-1].device_us-chosen[0].device_us)/1e6,
                csv_path=path.relative_to(self.folder).as_posix(),feature_names=FEATURES,
                calibration_id=self.meta["calibration_id"],data_quality_valid=True)
            save_json(path.with_suffix(".json"),meta)
            entries.append({"sample_id":sample_id,"dataset_label":e["dataset_label"],"intended_gesture":target,
                "is_correct_for_intended":False,"mistake_id":e["mistake_id"],"observed_valid_gesture":e["observed_valid_gesture"],
                "global_class_label":e["global_class_label"],"sample_count":len(matrix),"duration_s":e["duration_s"],"csv_path":meta["csv_path"]})
            samples.append(matrix);boundaries.append(boundaries[-1]+len(matrix));labels.append(e["dataset_label"])
            targets.append(target);other.append(e["observed_valid_gesture"]);sample_ids.append(sample_id)
        if entries:
            with (self.folder/"manifest.csv").open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=entries[0].keys());writer.writeheader();writer.writerows(entries)
        else:
            (self.folder/"manifest.csv").write_text("sample_id,dataset_label,intended_gesture,sample_count\n",encoding="utf-8")
        np.savez_compressed(self.folder/"wrong_examples.npz",values=np.concatenate(samples) if samples else np.empty((0,9),dtype=np.float32),
            row_splits=np.asarray(boundaries,dtype=np.int64),labels=np.asarray(labels,dtype=str),intended_gesture=np.asarray(targets,dtype=str),
            observed_valid_gesture=np.asarray(other,dtype=str),sample_id=np.asarray(sample_ids,dtype=str),feature_names=np.asarray(FEATURES),
            candidate_detector_label=np.asarray(["intentional_attempt"]*len(samples),dtype=str))
        save_json(self.folder/"events.json",self.events)
        self.meta.update(status="complete",finished_local=datetime.now().astimezone().isoformat(),stats=self.stats,
            accepted_wrong_counts=repetitions,accepted_wrong_total=len(entries),export_format="variable-length 9-feature CSVs and flat NPZ with row_splits")
        save_json(self.folder/"session.json",self.meta)
        (self.folder/"README_AI.txt").write_text('''DELIBERATE WRONG GESTURE EXAMPLES

wrong_examples/<intended_gesture>/: CSV files are variable-length wrong attempts
for that target, with exactly nine columns: ax ay az gx gy gz thumb index middle.
IMU is m/s^2 including gravity and rad/s without bias subtraction. Fingers are
binary 0 NOT_BENT / 1 BENT. No raw ADC, timestamps or model scores in model CSVs.
Matching JSON gives the intended gesture, mistake, quality and timing.
Valid/accepted refers to data quality, not a correct gesture.

manifest.csv lists the samples. wrong_examples.npz stores concatenated values
and row_splits; it does not pad or stretch a short action to three seconds:
  z=np.load('wrong_examples.npz',allow_pickle=False)
  clip_i=z['values'][z['row_splits'][i]:z['row_splits'][i+1]]
Each clip has its own actual number of frames. Handle cropping/padding/masks
according to your model. Do not interpolate binary finger states as angles.

IMPORTANT: wrong for SIT does not necessarily mean wrong for ALL commands.
is_correct_for_intended=False is the direct operator label. If observed_valid_gesture
names another valid class, keep that label rather than calling it background.
global_class_label is null if unknown and needs review. It is background only
when the operator explicitly selected no_valid_command. No numeric class ID
is imposed. Suggested mistakes are collection prompts, not authoritative AI labels.

These are intentional command attempts for the FINAL gesture recognizer/rejection
logic. Do not automatically use them as background negatives for the LOCAL
candidate detector: an incorrect attempt may still need upload so voice/gesture
mismatch can be reported to the user. candidate_detector_label records this intent.

stream.csv is the continuous original sensor/diagnostic stream. events.json
also retains rejected/cancelled brackets. Only sensor-valid accepted wrong
attempts appear under wrong_examples/. Manual boundaries are coarse brackets,
not measured physical onset times. Keep recordings grouped when splitting data.
''',encoding='utf-8')
        archive=self.folder.parent/("Milo_Wrong_Actions_"+self.folder.name+".zip")
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
            for file in sorted(self.folder.rglob("*")):
                if file.is_file() and file.suffix!=".tmp":z.write(file,file.relative_to(self.folder))
        return archive
