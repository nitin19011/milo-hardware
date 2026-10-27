Milo three-second training collector - BINARY finger states (18 Oct)

1. Upload MBF_v1/MBF_v1.ino to FireBeetle ESP32 using Arduino IDE.
2. Unplug USB and use battery power. Use your usual hotspot and laptop MQTT broker.
3. Run START_COLLECTION.bat. Dependencies are checked; use SETUP_ONCE.bat only if requested.
4. Start new session. Do the two short fit checks: relaxed hand, then comfortable fist, 2 seconds each.
5. Collect 10 good samples of each gesture in sequence. Every sample is 3 seconds: prepare for 1 second, then act at GO and finish during the next 2 seconds.
6. Keep / Repeat each take. After 70 accepted samples, send datasets/Milo_AI_Training_....zip to your AI teammate.

Inputs: six IMU axes + thumb/index/middle states, 0=NOT_BENT, 1=BENT. Continuous ADC is NOT a model input.
Firmware determines states continuously, including between recordings. Export never resets them at clip boundaries.
State thresholds match the latest 18 Oct demo correction, with hysteresis:
thumb: bend >=1460, release <=1420
index: bend >=1596, release <=1533
middle: bend >=3480, release <=3460
Keep 47k resistors. The fit checks verify these work for the current glove fit; they do not silently change thresholds.
If a check repeatedly fails, save and stop, and send the partial local session ZIP. Do not force gestures past a failed check.
Start a NEW session: older two-second or differently calibrated sessions cannot be resumed into this protocol.
RESUME_COLLECTION.bat fills remaining samples; it performs the two fit checks again.
For throws, loosely grip before GO, then swing and open your fingers together. Keep your hand open briefly afterwards.
The app requires a release transition in at least one finger after GO, but you still judge whether the motion was correct.
Raw ADC messages stay in the separate LOCAL raw_stream archive for debugging. The AI ZIP contains state-only finger features.
Motor stays off throughout training. Voice prompts are not audio recording; this is glove gesture training.

Loose grips need not mark all three fingers BENT. The fit check uses a comfortable fist instead.
Firmware profile is binary_flex_v5 and session protocol is v7_3s; flash the included MBF_v1 before collecting.
AI tensors are (N,150,9); the default X removes session gyro bias, while X_raw preserves physical IMU values like the demo.
The one-second preparation is INSIDE the three-second clip. Keep this cue alignment in mind when training for natural demo gestures.
