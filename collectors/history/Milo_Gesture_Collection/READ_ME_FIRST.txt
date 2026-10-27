MILO PERSONAL GESTURE COLLECTION - 12 OCTOBER 2026

START WITH THE THROW PILOT, NOT A LARGE DATASET
1. Upload MBF_v1/MBF_v1.ino from this package (updated main firmware).
2. Disconnect USB and use the glove battery. Keep your usual Mosquitto broker running.
3. Double-click Run_Throw_Pilot.bat. This records five examples each of overhand throw,
   underhand throw and background, plus three short calibration poses.
4. Send the resulting session ZIP from datasets for waveform/release review.
5. Once the pilot is consistent, collect other classes or full training sessions.

If dependencies are missing: py -m pip install -r requirements.txt
Broker default is 172.20.10.2. For another address, append --host YOUR_CURRENT_IP to a launcher,
or edit MQTT_BROKER_IP before uploading the sketch if the ESP's broker address changed.
The main normal glove topic remains sensor/glove/gesture; collection tags are additional fields.

GESTURE DEFINITIONS
come: one clear index beckon towards yourself.
sit: deliberate downward point, index extended, thumb and middle bent.
paw: upward-facing open palm, measured fingers extended.
spin: point, then turn the hand clockwise once, as viewed by the wearer. No roll-over class.
bang: index and thumb extended, middle bent (detailed-proposal default; confirm with team before final collection).
throw_overhand: loose imaginary-ball grip, overhand swing, finger release.
throw_underhand: loose imaginary-ball grip, underhand swing, finger release.
background: rest, fist only, overhand/underhand swings WITHOUT release, open-hand sweeps and ordinary movement.
Definitions are in gestures.json. Any change creates a different definition fingerprint and sessions will not be silently merged.

THROW TECHNIQUE
Use an empty hand to simulate holding the virtual ball. Grip comfortably, not a tight fist.
Your fingers need not cross a BENT threshold: continuous ADC values are the model inputs.
Calibrate the natural loose grip separately from open hand and full fist.
In overhand throws, begin near/behind the shoulder; release naturally during the forward throw.
In underhand throws, begin near the hip and swing forward from below; release naturally.
After release, hold the fingers open briefly, then return to neutral.
One throw per clip; do not perform repeated throws in one positive recording.
Do not force an identical release instant. Include natural small differences in speed and grip across repetitions.
If you forgot release, pressed a cable, or performed the wrong gesture, redo/skip that clip.

TIMING
Each gesture recording is 2 seconds / 100 samples at 50 Hz. No extra countdown is added.
Press Enter to start recording and prepare during the lead-in; the GO beep starts the action.
  Overhand/underhand throws: 0-1 s prepare a loose ball grip; 1-1.5 s swing AND
    open fingers together; 1.5-2 s follow through naturally with fingers open.
  come: 0-0.5 s neutral; 0.5-1.5 s one clear index-finger beckon; 1.5-2 s relax.
  sit: 0-0.5 s neutral; 0.5-1.5 s point down and briefly hold; 1.5-2 s relax.
  paw: 0-0.5 s neutral; 0.5-1.5 s present palm up and briefly hold; 1.5-2 s relax.
  spin: 0-0.5 s neutral; 0.5-1.5 s point then turn clockwise once; 1.5-2 s relax.
  bang: 0-0.5 s neutral; 0.5-1.5 s form finger gun and briefly hold; 1.5-2 s relax.
  Background swings WITHOUT release use the same timing as throws. Other background
    variants use the 0.5-second lead-in / 1-second movement / 0.5-second finish.
The finish beep is guidance: complete follow-through rather than abruptly stopping.
Instructions are explained once per class/variant, with short prompts thereafter.
The export also provides a fixed 0.5-2-second / 75-sample model view for EVERY class.
This view contains the throw action plus context; its bounds do not depend on the label.
The full 100-sample clip is the recommended starting input and remains authoritative.
Cues are NOT exact annotations of motion/release; raw clips allow later human event cropping.
Timing is based on Nitin's measured pace. If a gesture regularly runs past STOP, adjust
that protocol before collecting the final dataset; do not force unnatural movements.
This v2 protocol changes the timing and come to ONE beckon. Collect all final sessions
with the same version; old six-second sessions are still readable but cannot be merged
silently with v2. No further firmware upload is needed for this timing-only revision
if the updated collection-capable MBF_v1 is already on the glove.

CALIBRATION EACH TIME YOU PUT THE GLOVE ON
The collector asks for three 4-second poses: straight/open hand, comfortable fist, natural ball grip.
It records the same raw sensors and computes session open/fist values plus stationary gyro bias.
Finger normalisation is (raw - open) / (fist - open). Ball grip may be e.g. 0.2-0.5, not automatically 1.
Values are NOT clipped to 0-1; real variation and faults remain visible.
If a calibration pose has a rail spike, IMU fault or missing data, it is saved and retried.

COLLECTING A PERSONAL DATASET
Run_All_Gestures_Pilot.bat: three repetitions per class to confirm poses and formats.
Run_Training_Session.bat: ten repetitions per class, shuffled within each repetition round.
After the pilot, a starting target is 20-30 CLEAN training recordings per gesture across at least two or three wear sessions.
Reserve separate wear sessions for validation/testing; more samples may be needed for confusing pairs.
An example four-session starter plan:
  Sessions A/B: ten examples per class each, --role train (20 training examples/class).
  Session C: ten examples/class, --role validation.
  Session D: ten examples/class, --role test; keep untouched while choosing thresholds/models.
Optional extra training session: another ten/class before model selection.
Re-wear/refit the glove between sessions. Vary comfortable speed/starting position, but preserve gesture meaning.
Roles can be set as launcher arguments, e.g. Run_Training_Session.bat --role validation.
Without --role, sessions stay unassigned. The exporter NEVER randomly splits frames or clips for you.
This is personal training for Nitin; it does not establish accuracy for other wearers.

QUALITY AND THE MIDDLE FLEX ISSUE
All raw attempts are saved. Rail spikes, failed I2C reads, clipping, missing sequences,
incomplete clips and queue drops are quarantined and excluded from training exports.
The known middle-channel issue is not hidden or smoothed away.
You can capture a pilot now, but final training data must use clean sensor recordings.
Warnings such as out-of-calibration finger values or delayed cue acknowledgement require signal review before export.
User accept/redo confirms gesture performance; it does not override hard sensor-quality failures.

REVIEW AND RELEASE ANNOTATIONS
Every session contains review.html. Open it in a browser to inspect the plots.
Select a clip, then click a plot to mark action start, finger release (throws), and action end.
Review the waveform before accepting signal warnings. Quarantined clips stay excluded.
Download annotations.json, then apply it:
  py review_session.py SESSION_FOLDER --annotations PATH_TO_DOWNLOADED_ANNOTATIONS.json
This updates the per-clip metadata and regenerates that session's export/reviewer.
A release candidate is provided as a heuristic only; it is NOT ground-truth labelling.
Initial accept of a throw means you confirmed that you released the fingers, not that you specified the exact release time.
Optional reference video can assist annotation, but no video is required by the scripts.

FILES FOR THE AI TEAMMATE
Each session ZIP contains session.json, calibration.json, raw_stream.jsonl, events.jsonl,
clips/*.csv, clips/*.json, review.html and export/*.
The export provides dataset.npz, .npy arrays, all_samples.csv, clips.jsonl, dataset.ts and labels.txt.
See AI_HANDOFF.txt for shapes, units, preprocessing and split guidance.
Optional .pt/.h5 converters are included for your teammate's environment.
To combine session folders:
  py dataset_tools.py SESSION_A SESSION_B SESSION_C SESSION_D --output combined_training_export
Do not combine sessions with different gesture definitions or hardware/preprocessing profiles.
After changing annotations, rerun any combined export and rebuild a handoff ZIP.

MAIN FIRMWARE CHANGES
Ranges: +/-16 g and +/-2000 deg/s, 21 Hz filter, 50 Hz sampling.
16 g gives headroom after the retest's isolated 8 g clipping sample.
Checked 14-byte I2C reads make imu.valid meaningful; range register read-back verifies settings.
IMU reinitialisation is attempted after faults, with a bounded I2C timeout.
ADC rail mask and error/drop counters are added. Raw bad readings are still transmitted.
Legacy bend states hold their last value during a rail fault; consumers must honour the quality mask.
Thumb's legacy threshold is 1500 (previously 1600), retaining 20-count hysteresis.
This gives more margin above mounted straight-hand readings and below the tested fist readings.
Index/middle thresholds remain 1800. AI features use continuous values, not these state thresholds.
No automatic moving-hand gyro calibration is imposed at startup; session calibration is explicit and off-board.
Existing Wi-Fi/MQTT behaviour and explanatory comments are retained.
The old working main file is backed up before installation. Frozen submission files are not edited.
