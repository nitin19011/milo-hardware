MILO - AUTOMATIC GESTURE DETECTOR DATA COLLECTION

This collects TRAINING DATA for a future local detector. There is no trained
gesture detector on the ESP yet. No mic, MQTT broker, internet or fist trigger.
All three fingers are enabled, using the 23 October calibration.

FLASH ONCE
1. Open GloveCandidateLogger/GloveCandidateLogger.ino in Arduino IDE.
2. Board: FireBeetle-ESP32 (DFR0478). Install ArduinoJson if it is absent.
   The build was checked with ESP32 Arduino core 3.3.11 / ArduinoJson 7.4.3.
3. Upload to your glove. Close Serial Monitor and Serial Plotter afterwards.
4. Run START_COLLECTION.bat. Python 3 with Tkinter is needed; pyserial is installed
   automatically if missing. This sketch replaces the current glove demo sketch.

USB COLLECTION
Choose USB, choose the glove COM port, and click Connect.
Leave USB connected. Streaming and a new dataset session start automatically.
The collector uses 230400 baud; Serial Monitor must be closed.

UNTETHERED WI-FI COLLECTION
1. Put the laptop and glove on the same 2.4 GHz Wi-Fi / phone hotspot.
2. Leave glove USB attached for ONE-TIME setup. In the UI, leave it disconnected
   and click Set up Wi-Fi via USB. Enter hotspot name/password and the laptop's
   Wi-Fi IPv4 address. The proposed laptop IP can be changed if it is a VPN or
   Ethernet address. The COM port must belong to this glove.
3. Click Save to glove & use Wi-Fi. The UI starts listening automatically.
4. Check that LIVE sensor readings continue, then unplug USB and use battery.
   If unplugging resets the ESP, wait for LIVE to return before labelling.
The glove remembers these Wi-Fi/destination settings in its own flash. They are
not written into the dataset or the Python files. On later runs select Wi-Fi and
Connect. Reconfigure if the laptop IP, hotspot or password changes.
Allow Python through Windows Firewall on your private local network if prompted.
UDP port is 25400. This is a local, unencrypted collection stream, not the TLS demo.
There is no delivery guarantee; sequence gaps, faults and restarts are recorded.

FAST GESTURE COLLECTION
- Wear the glove normally. Set Wearer and Session role before connecting.
- Default target is 10 GOOD takes for each of the 7 gestures, sequentially.
- Press SPACE just BEFORE starting your action.
- Do the action naturally, then press SPACE immediately AFTER it finishes.
- That is saved automatically. Repeat immediately: no countdown, playback,
  fixed 3-second lock, review/accept screen or forced rest between takes.
- The UI advances to the next gesture after 10 accepted takes. You may change
  the target or select another gesture with buttons / keys 1..7.
- Esc cancels a mistaken active take. Backspace discards the last completed take.
  You can also select a recent take and click Discard selected take.
- Move at different speeds / sizes and normal arm positions. Don't always start
  in a special fist pose. The motor stays OFF. No speech needs to be recorded.
- For throws, use a LOOSE imaginary-ball grip and release/open your fingers
  during the throw, rather than squeezing a full fist first.
Very short, very long, faulty, clipped or incomplete gesture brackets are not
counted towards the target. Their raw readings remain saved for diagnosis.

BACKGROUND / EVERYDAY MOVEMENT
The detector also needs non-command examples. Select Everyday activity, choose
the activity label, press Space once, move normally, then Space to finish.
There is no maximum duration or fixed waiting period. Aim for 10-15 minutes total:
walking, typing, reaching, scratching, talking with your hands, casual pointing,
wrist turns, opening/closing fingers without a command and adjusting the glove.
Only label a segment background if it contains NO deliberate command gesture.
If you accidentally perform a command during it, cancel/discard that segment
and label a new one; its raw stream is retained.

SAVE / SEND
Click End session & ZIP. This also finishes an active bracket. A ZIP is generated in the
background; you can start another session immediately while it saves.
Closing the window also saves a ZIP automatically, discarding an unfinished
active bracket. Stream CSV flushes every
second and event annotations are saved on every mark, so raw files survive a
crash even if no final ZIP was created. Don't force-terminate while saving.

Send the file displayed as SEND THIS ZIP:
  datasets/Milo_Candidate_Data_<session>.zip
Raw session folder:
  datasets/<session>/

FIRST COLLECTION
Collect 10 natural takes per gesture and everyday movements. Then make a NEW
session marked validation, preferably after taking the glove off and putting it
back on. Keep whole sessions separate; don't randomly split overlapping windows.
Do not assume the first collection proves 99% detection: we train and measure
event coverage and detection delay afterwards, then target any missed cases.

WHAT IS SAVED
stream.csv: every received raw stream frame, device/host timestamps, IMU SI axes,
  3 binary fingers, raw ADC diagnostics, fault flags, sequence/order/drop data.
events.json + events.csv: gesture/background brackets, labels, status and quality.
session.json: wearer, session role, calibration and acquisition metadata.
gesture_clips/<gesture>/: accepted variable-length brackets with up to 1 second
  of context before and after. Neighbouring gesture IDs are retained in context.

IMPORTANT FOR TRAINING
The Space presses bracket an action; they are not precise physical onset labels.
Both original host monotonic marks and estimated device positions are kept.
USB/Wi-Fi one-way latency is not known; arrival jitter is diagnostic, not a bound
on absolute alignment. Unlabelled/context frames are NOT automatically negatives.
Long background segments may contain bad windows: filter flags/gaps per window.
No synthetic missing samples or ADC-as-model-feature conversion is performed.
The future 3-second upload clip is separate from these variable training segments.
This package does NOT modify the existing mic, glove demo or earlier datasets.
