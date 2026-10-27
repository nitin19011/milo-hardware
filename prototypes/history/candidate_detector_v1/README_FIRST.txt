MILO - FIRST LOCAL GLOVE DETECTOR / LIVE TEST
25 October 2026

The model now runs ON THE GLOVE ESP32. No fist trigger, mic, MQTT, internet
inference service or mandatory delay before an action.

WHAT WAS TRAINED
- Original recording ZIP was not edited.
- 9 uncertain brackets were held aside: 4 short Come and 5 short overhand.
  They are not assumed to be mistakes, and are not used as negative examples.
- Remaining 132 provisional gesture brackets plus the labelled everyday data.
- 78 gesture brackets fitted the trees; 26 calibration + 28 other brackets were
  used for development checks. Whole event groups were kept separate.
- Fitting used the five most active windows per gesture bracket to reduce the
  preparation/rest contained in coarse manual labels. This is weak supervision.
- Selected model: 24 shallow decision trees using past 0.8 seconds of IMU and
  binary finger features. Evaluates every 0.1 second. No TensorFlow runtime.
- Raw flex remains diagnostic; the selected forest does not use raw ADC features.

HONEST STATUS
The initial stricter threshold missed one Sit bracket. A permissive 0.10 setting
caught 54/54 brackets not used to fit tree weights in this SAME recording session,
with about 2.5 extra proposals/minute on its development background blocks.
The threshold was inspected/tuned using this session, so this is NOT a final
held-out test or evidence of 99% real-world recall. Operator brackets are not
exact motion onset labels. A fresh worn-glove session is needed now.

FLASH
1. Open GloveCandidateDetector/GloveCandidateDetector.ino.
2. Board: FireBeetle-ESP32 / DFR0478. ArduinoJson library is required.
3. Upload. Close Serial Monitor / Plotter.
4. Run START_LIVE_TEST.bat. Only Python/pyserial/Tkinter are needed for the UI.

CONNECT
USB: choose glove COM port and Connect. Baud rate is 230400.
Wi-Fi: same private Wi-Fi / hotspot as laptop, then select Wi-Fi and Connect.
If you configured the previous logger, its stored Wi-Fi settings are reused.
Otherwise use Set up Wi-Fi via USB once, then check LIVE readings and unplug.
The saved laptop IP must still be correct. Local UDP port 25400; no MQTT broker.
This is an unencrypted local test stream; passwords are stored on the glove,
not in this package or dataset. Arduino's erase-all-flash option can clear them.

WATCH IT WORK WITHOUT SPACE
- Move naturally: the AUTO counter increments when the glove proposes a clip.
- AI is a model score, not a calibrated probability. Threshold is deliberately
  low (0.10) because missing a command matters more than extra recordings.
- It examines the previous 0.8 s; one valid second of history is needed once at
  startup/fault recovery to supply pre-roll. There is no per-action countdown.
- Proposals may repeat at most once per second during sustained motion; there
  is no requirement to straighten the fingers or become still to re-arm.
- There are no motor buzzes. This avoids disturbing the movement being tested.

QUICK INDEPENDENT TEST
Use the UI's default validation role. The default is 5 takes per gesture; no
need to redo your original collection. Include gentle/subtle as well as normal
gestures, especially Come and Sit. Do not exaggerate to make the detector fire.

Space BEFORE moving -> perform naturally -> Space AFTER finishing.
Space is ONLY a ground-truth bracket for evaluation; it does NOT trigger the
model or automatic clip proposals. Esc cancels a bad bracket; Backspace undoes.
Take as many as you like; no countdown, forced rest or playback. Ordinary hand
activity still needs to be tested, e.g. a couple of minutes in Everyday mode.

End session & ZIP saves automatically. Send:
  datasets/Milo_Candidate_Data_<session>.zip

WHAT THE AUTOMATIC CLIPS MEAN
The ESP keeps a 3-second sensor history and reports each proposal with its
original sequence/time. Each proposal requests 1 second before detection plus
2 seconds afterwards. The laptop extracts the corresponding 150 rows from the
continuous telemetry under automatic_clips/, with candidate_proposals.json.
Missing/truncated/faulty windows are marked invalid, never silently filled in.
There is no duplicate bulk transmission of each overlapping window during tests.
Ending a session before post-roll is available can leave a partial window.
Manual gesture_clips/ are annotation brackets, separate from automatic_clips/.

THIS IS A GLOVE-ONLY PROTOTYPE
It does NOT send anything to Ultra96, command Milo, or synchronize with a mic yet.
Those are separate integration steps. Existing mic firmware needs buffered
retrospective capture support before it can extract the same past interval.
Glove proposal times are device-monotonic, not UTC. Shared clock mapping is still
needed for pairing. Overlapping proposals also need deduplication/queuing before
they can become final AI commands. Original demo/collection folders are unchanged.

FILES
model.json: exported trees and feature definitions.
training_report.json: explicit development results, exclusions and limitations.
initial_training_report.json: earlier stricter-setting results, retained honestly.
window_scores.csv / training_windows.npz: offline development diagnostics only.
training/: reproducible feature/training/export scripts and annotation review IDs.
GloveCandidateDetector/: flashable source, feature extraction and model header.
collector_core.py / collector_ui.py: live validation and automatic window export.

RETRAINING (not required to flash/use the live UI)
Install training/requirements.txt in a suitable Python environment.
From this folder:
  py -3 training/train.py <original-recording.zip> training/annotation_review.json
  py -3 training/export_header.py
The original source ZIP is not duplicated in this package; its SHA256 is recorded.
Do not treat these development checks as independent generalization evidence.

TESTS
  py -3 -m unittest test_detector test_collector
See VALIDATION.txt. No hardware was flashed by the assistant.
