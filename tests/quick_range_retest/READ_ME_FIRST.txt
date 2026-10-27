QUICK EXPANDED-RANGE RETEST

Only five phases, 40 seconds of actual recording:
  1. Supported stillness: 5 seconds
  2. Quick palm flips: 10 seconds
  3. Brisk direction changes: 10 seconds
  4. Moving open-hand/fist cycles: 10 seconds
  5. Final supported stillness: 5 seconds
Allow approximately 1-2 minutes including instructions/countdowns, plus the one-time firmware upload.

1. UPLOAD THE NEW DIAGNOSTIC SKETCH ONCE
Open Glove_Quick_Range_Retest/Glove_Quick_Range_Retest.ino in Arduino IDE.
Use your usual FireBeetle-ESP32 board, USB port and installed PubSubClient library.
Network settings are copied from your working diagnostic sketch (broker 172.20.10.2, port 1883).
Check/update the broker IPv4 if it changed, then upload.
Disconnect USB and power the glove from its battery for the exercises.

2. RUN THE SHORT GUIDE
Keep your existing Mosquitto broker running.
Double-click Run_Quick_Retest.bat.
For a changed broker address:
  py quick_range_retest.py --host YOUR_CURRENT_IP --speak
The program rejects the old firmware/ranges to avoid a misleading comparison.
Keep guided_glove_test.py beside quick_range_retest.py; it supplies shared helper functions.
The receiver dependency is already installed if your last tests worked. If needed:
  py -m pip install -r requirements.txt

3. FOLLOW THE PROMPTS
Repeat the same motions and approximate effort as the previous stress test.
Move after the countdown and GO beep; stop at the ending beep.
Brisk comfortable motions, no impacts or deliberate pulling on wires.
No isolated flex calibration or complete original test sequence is repeated.
The flex channels are still logged to detect wiring changes while moving.

4. SEND THE RESULT
Send the new ZIP shown on screen from quick_retest_results.
Contains CSV, raw JSON, events, manifest and summary with explicit range metadata.
Connection pauses and restarts continue to be recorded; Ctrl+C saves a partial result.

CHANGES
Gyro range: +/-2000 deg/s (previously +/-500).
Acceleration range: +/-8 g (previously +/-4).
Gyro conversion: 16.4 raw counts per deg/s.
Acceleration conversion: 4096 raw counts per g.
Physical units remain rad/s and m/s^2; raw counts are also preserved.
Range register read-back verifies settings before reporting valid IMU data.
Unchanged 50 Hz sampling, 21 Hz filter, ADC reading method, flex pin mapping and original MQTT broker.
This package updates the diagnostic firmware; the main MBF_v1 project file has not been edited.

Compare clipping counts, physical peaks, continuity and before/after stillness with the prior stress run.
A sample clipping at the new range still means its true peak exceeds the recorded limit.
The package sketch contains your copied Wi-Fi settings. Result ZIPs contain no Wi-Fi password.
