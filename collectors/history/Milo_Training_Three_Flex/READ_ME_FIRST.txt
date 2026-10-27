Milo - three-finger gesture collection

Upload MBF_v1/MBF_v1.ino to the glove first. This package is separate from the previous thumb/index recordings.
The replaced middle sensor uses GPIO39. Keep your existing 47k resistor for this trial.
Firmware records all three continuous flex readings; no new hard-coded threshold is required for collection.
The motor stays OFF, including at startup. Rejection feedback belongs to the eventual integrated system.

1. Run SETUP_ONCE.bat if dependencies are not already installed.
2. Keep the same laptop broker/hotspot running as before. Upload over USB, then unplug and power the glove from its battery.
3. Wear the glove normally. Run CALIBRATE_FIRST.bat.
4. Record three 2-second poses: open hand, comfortable full fist, loose imaginary-ball grip. Hold still BEFORE pressing Record.
5. Try bending and straightening each finger in the live test. The app shows independent BENT / NOT BENT states and raw readings.
6. Press Finish and save. Send Milo_Calibration_....zip from this package's datasets folder for review.

Calibration saves open/fist/loose medians, noise, bend direction and trial bend/release thresholds for all three fingers.
Thresholds use 55% of open-to-fist span to enter BENT and 45% to release, with bending direction handled automatically.
For example, open 3300 and fist 3500 gives BENT at 3410 and release at 3390. Actual calibration supplies your values.
A span under 100 counts, excessive noise, ADC rail, missing data or IMU failure requires repeating/checking the hardware.
Small stable spans can pass; passing calibration alone does not prove gestures will classify accurately.

After calibration review: use RESUME_COLLECTION.bat while the SAME fit/resistor is unchanged; this retains calibration.
If the glove was removed/refitted, or wiring/resistor changed, use START_COLLECTION.bat -> Start new session instead.
Collection: 2 seconds at 50Hz, 1 second preparation then 1 second movement/follow-through.
Finish 10 good samples of each class in sequence; Keep / Repeat controls remain unchanged.
Final AI ZIP contains class folders, CSV/JSON, NPZ/NPY/JSONL/TS, metadata, calibration and optional format converters.
New inputs have N x 100 x 9 shape: ax ay az gx gy gz thumb index middle.
Do not mix the old 8-channel recordings into this dataset or invent their missing middle values.
