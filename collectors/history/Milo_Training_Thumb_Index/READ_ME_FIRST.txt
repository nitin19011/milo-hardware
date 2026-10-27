MILO - DIRECT GESTURE TRAINING COLLECTION (15 OCTOBER 2026)

HARDWARE CHANGE: THUMB + INDEX ONLY
The middle flex sensor has failed. GPIO39 is no longer sampled, calibrated or
used to decide whether a take is good. It is OMITTED from all training features:
ax, ay, az, gx, gy, gz, thumb, index (eight inputs). No zero or fake middle readings.
Thumb/index rail checks and all IMU/integrity checks remain active.
Start a NEW dataset with this package; old three-finger sessions are incompatible.

MOTOR CHECK
The NEW main sketch uses D2 / GPIO25 -> module IN. Module VCC -> FireBeetle VCC,
module GND -> FireBeetle GND, as wired. At EVERY power-on/reset it gives three
short buzzes (150 ms ON, 150 ms OFF), turns off, and waits another 700 ms before
starting sampling/network tasks. It never turns on during gesture/calibration capture.
After uploading, touch the module and check for the three pulses. If you missed
them, press the glove RST button BEFORE recording. Do not reset mid-recording.
The collector records your yes/no/not-checked report; firmware cannot electrically
verify that a physical motor moved. A failed motor check does not block sensor collection.
STARTUP_MOTOR_TEST in the sketch can be set false later when this check is no longer needed.

NEW DESKTOP WINDOW / SEQUENTIAL COLLECTION
Double-click START_COLLECTION.bat to open the collection window.
Click Continue saved session to keep your existing good samples. If you started
from a different extracted folder, click Choose saved session and select its
datasets/SESSION_ID/session.json. Start new session is for a fresh glove fit.
Before switching from an already-running terminal collector, stop it with q or
Ctrl+C and let it finish saving. Do not run the two collectors together.

Order is FIXED: Come x10 -> Sit x10 -> Paw x10 -> Spin x10 -> Bang x10 ->
Overhand throw x10 -> Underhand throw x10. It never shuffles the actions.
On resume, existing accepted samples count towards each gesture's ten. It fills
the earliest incomplete gesture first, then moves forward through the list.

The window keeps instructions, current sample (e.g. Come 2/10) and total progress
visible. Click Record 2 seconds, then Keep sample or Repeat. Repeat immediately
starts another take after the normal one-second preparation. Save and stop
retains accepted samples and produces the partial ZIP. The finished screen has
an Open ZIP folder button. Keyboard shortcuts: Enter record/keep, R repeat,
Q save/stop. A fault message names thumb/index when that channel hits a limit.

This UI/order revision changes no sensor features or recording duration. Existing
thumb/index v4 recordings and calibrations remain compatible. NO new ESP upload
is required if the thumb/index + motor-check firmware is already on your glove.
The original console interface remains in START_COLLECTION_CLI.bat.

WHAT YOU WILL COLLECT
10 clean, wearer-confirmed examples for EACH of these seven actions:
come, sit, paw, spin, bang, throw_overhand, throw_underhand.
Total: 70 examples. This goes straight into collection; there is no pilot stage.
The software checks sensor/recording integrity. You confirm the prompted action
was performed correctly; there is no trained model judging your movement yet.

START
1. Extract this WHOLE package to a normal folder before running it.
2. Upload the NEW included MBF_v1/MBF_v1.ino to the GLOVE FireBeetle ESP32.
   This version disables middle-flex sampling and adds the startup motor check.
   The previous three-finger firmware will not work with this collector.
   If running from your project MBF_v1/Training_Thumb_Index folder, open the
   main MBF_v1.ino in its parent folder instead; it is the same updated sketch.
   Board: FireBeetle-ESP32. Required Arduino library: PubSubClient, plus ESP32
   core's built-in Arduino/Wire/WiFi libraries. Do not upload it to the collar.
3. Use your normal Wi-Fi and laptop Mosquitto broker; default broker IP is
   172.20.10.2, port 1883. Firmware settings are near the start of the .ino.
   If your network changed, update the firmware Wi-Fi/broker settings and
   upload, then launch with --host YOUR_LAPTOP_IP. The laptop broker must be
   reachable from the glove, not only from localhost.
4. Run SETUP_ONCE.bat if Python dependencies are not installed.
5. Disconnect the glove USB and run it on battery. Double-click START_COLLECTION.bat.

RECORDINGS ARE TWO SECONDS, INCLUDING CALIBRATION
First: three one-time, TWO-second poses: open hand, full fist, loose ball grip.
Press Enter while already holding each pose. This measures per-wear flex range
for thumb/index and stationary gyro bias; the calibration poses are not gesture training clips.

For each gesture:
  - Read the displayed action/phrase and click Record 2 seconds when ready.
  - 0-1 s: prepare. For throws, use a loose imaginary-ball grip, not a fist.
  - GO beep at 1 s: perform ONE action. Complete naturally before STOP at 2 s.
  - Throws: about 0.5 s swing WITH finger opening, then about 0.5 s follow-through.
  - Other actions: form/perform the gesture, hold briefly where appropriate,
    then relax. Do not repeatedly beckon/rotate/throw in the same recording.
  - Keep sample saves a correctly performed take; Repeat retries; Save and stop exits safely.
  - Sensor failures/warnings never count. The same sample is repeated.
There is no separate countdown, four-second gesture capture or required pilot.
Do not abruptly freeze at STOP if still following through. Instead, repeat that
take: only keep recordings containing the full action and useful final context.
Natural small changes in timing, grip and motion are welcome; preserve the action.

ACTION DEFINITIONS AND SPEECH
Perform the same full-hand poses, although middle bend is no longer measured.
Keep paw palm-up and bang pointing forward so their IMU orientation differs.
come: one index-finger beckon towards yourself. Say "Milo come".
sit: point down; index extended, thumb/middle bent. Say "Milo sit".
paw: present open palm up. Say "Milo paw".
spin: point, then turn the hand clockwise from your view. Say "Milo spin".
bang: finger gun, index/thumb extended and middle bent. Say "Milo bang".
throw_overhand: loose ball grip, overhand swing and finger release. Say "Milo fetch".
throw_underhand: loose ball grip, underhand swing and finger release. Say "Milo fetch".

Say the phrase naturally during the capture, near the action. You can start
speaking during preparation; do not wait until the phrase is finished to move.
In the final project voice recognition and glove classification will be matched
over time. A two-second glove window is independent of the collar WAV duration.
This collector records GLOVE SENSORS ONLY. No collar/PC microphone is required.
Spoken phrases in metadata are prompts, NOT audio recordings, recognised words
or measured voice timestamps. No speech/gesture synchronisation is claimed.

STOPPING AND RESUMING
Save and stop (or q/Ctrl+C in the console) retains recordings and creates a PARTIAL ZIP.
RESUME_COLLECTION.bat continues the latest session without restarting its count.
Only resume while the glove fit has stayed unchanged. If you remove/refit it,
START_COLLECTION.bat starts a new wear session with a new calibration.
Completing a session requires ten eligible examples per action; there is no skip
that can silently leave only nine. Accepted files are rechecked on resume/export.
Keep this window and the laptop awake during capture; do not run two collectors
against the glove at once. Data saves continuously to this package's datasets folder.

FILE TO SEND TO YOUR AI TEAMMATE
After 70 accepted recordings, the finished screen shows the ZIP path and Open ZIP folder:
  datasets/Milo_AI_Training_SESSION_ID.zip
Send THIS ZIP. It contains only eligible examples, labels, continuous readings,
timestamps, calibration, model-ready arrays, feature units and the AI handoff.
The code does not send anything to your teammate automatically.

A separate datasets/SESSION_ID.zip retains all raw attempts for troubleshooting;
do not use that archive as the curated training set. Failed attempts are not lost.
If stopped early, Milo_AI_PARTIAL_SESSION_ID.zip states the actual counts and is
never presented as the complete 70-example dataset.
No real training recordings are bundled with this SOFTWARE package.

OPTIONAL COMMANDS
  py collect_training.py --host YOUR_CURRENT_LAPTOP_IP
  py collect_training.py --resume-latest
  py collect_training.py --resume FULL_PATH_TO_SESSION_FOLDER
  py collect_training.py --speak
Speech prompts are off by default for quick collection; cues still beep/display.
All seven actions are collected in the fixed blocks of ten listed above.
The sensor data/labels are unchanged by this collection-order preference.
