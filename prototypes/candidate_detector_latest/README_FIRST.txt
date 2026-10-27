MILO - GLOVE DETECTOR V2: HARD-NEGATIVE UPDATE
25 October 2026

This is a new glove model plus a clearer live UI. Original firmware, v1 files,
recordings and ZIPs are unchanged.

USE THIS VERSION
1. Close the old v1 UI so it releases UDP port 25400.
2. Open GloveCandidateDetector/GloveCandidateDetector.ino FROM THIS V2 FOLDER.
   Arduino IDE can have another sketch with the same name open: check the folder.
3. Upload using FireBeetle-ESP32 / DFR0478. ArduinoJson library is needed.
4. Close Serial Monitor / Plotter, then run START_V2_LIVE_TEST.bat.
5. Connect via USB or Wi-Fi. Previous Wi-Fi settings on the glove are reused
   unless all flash was erased. One-time USB Wi-Fi setup is also available.

There is no mic, MQTT or fist trigger. Detection and the model run on the glove.
Do NOT run the old v1 UI for the new sketch. V2 transmits MILO3 telemetry; the
new UI explicitly warns OLD SKETCH if the glove is still running v1.

WHAT CHANGED
The two-minute labelled everyday recording was used as hard-negative training
material. Its unlabelled sections and your earlier unlabelled mixed session
were not guessed to be negative. Nine uncertain original action brackets remain
excluded and are not treated as mistakes or as background.

The new model has 32 shallow trees. It also uses relative raw-flex changes as
LOCAL trigger hints; the final Ultra96 gesture format of six IMU axes plus
three binary fingers is not changed. Existing main demo code was not edited.
These relative raw features use ranges/changes, not absolute ADC levels.

Development positive checks still hit all 54 original non-fitting gesture
brackets. Threshold was tuned using these development labels: this is NOT
independent evidence of 99% recall. Fitting used 78 other original brackets.

In the final ~23-second block of the NEW background recording, left out of
fitting and variant selection, the old model made 5 proposals and v2 made 0.
That is a promising short check, not a claim that all normal activity is solved.
The other negative calibration blocks and model comparisons are in the report.

CLEARER UI
- Large DETECTOR: POSSIBLE ACTION banner means the score currently passes the
  model threshold. DETECTOR: watching means it does not.
- Activity groups merge overlapping 3-second window requests for the summary.
- Window requests is the raw number of automatic proposed windows.
- Grouping does NOT discard windows or suppress decisions for a long cooldown.
  A new action during sustained movement can still propose another window.
- Group counts are not gesture-classification results. Final AI still determines
  the actual command. All raw proposals/windows remain in the saved dataset.
- The small score is not a calibrated probability.

QUICK CHECK - NO NEED TO REPEAT YOUR ORIGINAL DATASET
Try a few normal AND gentle real gestures, especially Come and Sit, plus the
ordinary movements that previously overtriggered. Check the green indicator.
Use Space before/after a real gesture only to LABEL it for validation, not to
trigger the detector. The UI defaults to validation and 5 takes per gesture;
this is optional guidance, not a fixed recording limit. No countdown or rest.
Everyday mode labels non-command movement: Space once, move normally, Space
again to finish. There is no required duration or fixed wait.
End session & ZIP, then send the displayed dataset ZIP.

AUTOMATIC WINDOWS
Each glove-generated proposal requests 1 second before detection and 2 seconds
afterwards. The ESP retains 3 seconds of sensor history; the laptop reconstructs
150 chronological rows from the continuous stream for inspection. No duplicate
bulk transmission of overlapping windows during testing. Incomplete, faulty or
missing windows are explicitly invalid, never silently filled.
Outputs: stream.csv, candidate_proposals.json, automatic_clips/,
automatic_activity_groups.json, events.json/csv and session.json.
Manual gesture_clips/ are separate operator brackets, not automatic windows.
Times are glove-monotonic. Mic ring buffers, shared clock mapping, MQTT upload
and final command deduplication remain separate future integration work.

DATA INTEGRITY
Source recordings and earlier versions were not changed. New results go into
this folder's datasets/. Wi-Fi credentials are not stored in the dataset.
Wi-Fi uses local unencrypted UDP port 25400; USB uses 230400 baud. Keep laptop
and glove on the same private local network. See model.json and training_report.json
for model/calibration identifiers and limitations.

TRAINING / TESTS
Runtime UI needs Python 3, Tkinter and pyserial only; no ML runtime on the PC.
Training scripts require training/requirements.txt. To reproduce, retain v1's
training_windows.npz and window_scores.csv plus the new labelled recording ZIP:
  py -3 training/retrain_hard_negatives.py --v1-folder <v1-folder> --hard-negative-zip <new-recording.zip>
  py -3 training/export_header.py
Do not run an initial v1 training script over this version.
Tests: py -3 -m unittest test_detector test_collector
Physical glove behaviour still needs your run; no 99% recall claim is made.
