GLOVE MOTION STRESS TEST

Keep the diagnostic sketch already uploaded for your last test.
No USB connection or firmware upload is needed for this package.
Power the glove from its battery; keep the existing MQTT broker running.

Extract this ZIP, then double-click Run_Stress_Test.bat.
It uses the same broker IPv4 as the previous test: 172.20.10.2.
For a changed broker address, open a terminal in this folder and run:
  py stress_glove_test.py --host YOUR_CURRENT_IP --speak
If Python reports a missing dependency:
  py -m pip install -r requirements.txt
The helper guided_glove_test.py must stay beside stress_glove_test.py.

11 phases: supported stillness, moderate wrist motion, quick palm flips,
arm sweeps, circles/figure-eights, brisk direction changes, and moving finger cycles.
Stillness checks are interspersed, with a final baseline check.
Read/listen to the prompt, press Enter, and move after the countdown and GO beep.
Stop at the ending beep. Use brisk comfortable motion without impacts or deliberate wire pulling.
The laptop countdown stays bounded even if wireless data disappears.
Data continues recording during pauses, reconnects and ESP restarts.
Before the next phase, the program waits for fresh samples; an unavailable phase is skipped.
Ctrl+C saves a partial result ZIP. Keep the laptop awake and nearby.

At the end send the NEW result ZIP shown on screen, under stress_results.
It contains samples.csv, raw_samples.jsonl, events.jsonl, manifest.json and summary.json.
All new-boot/idle/recovery data is saved. No Wi-Fi credentials are included in the result.

INTERPRETATION
Boot changes: the board restarted; the logs alone do not establish why.
IMU invalid samples: checked I2C reads failed.
Missing sequence numbers / rising queue counter: sample delivery or buffering lost readings.
Receive pauses with continuous timestamps/sequences: delayed delivery, not automatically a broken wire.
Near-rail flex readings or sudden unexplained baseline changes: candidates for wiring/fit review.
Gyro/acceleration clipping: the existing +/-500 deg/s and +/-4 g measurement ranges were exceeded.
Clipping alone is not an electrical disconnection; original ranges are intentionally preserved for comparability.
An old boot's retained OFFLINE message is stored separately from the active stream.

The original ESP acquisition labels remain authoritative for each phase.
Host labels supply context only for new-boot/unlabelled samples; delayed arrivals are not silently assigned a new ESP phase.
No pending movement command is queued to run later after reconnect.
This is evidence collection, not an automatic declaration that the hardware passes every motion.
