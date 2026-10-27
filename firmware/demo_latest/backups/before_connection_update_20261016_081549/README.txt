Milo checkpoint demo - glove + mic ESP32

Exact interaction:
1. Open the hand once to arm. Both devices need valid clocks and MQTT connections.
2. Hold a FULL fist for 2 seconds. The glove negotiates mic readiness during this hold.
3. The glove motor buzzes for 1 second.
4. At the end of that buzz, immediately perform the gesture and speak. Both devices record the next 3 seconds.
5. The glove motor buzzes for another 1 second when recording finishes.
6. After the ending buzz stops, the glove releases the upload gate. Both clips are sent to MQTT.
7. Open the hand again to rearm once both uploads finish.

There is deliberately NO extra settling delay after the first buzz, per the requested sequence.
Motor coast/vibration near the boundary still needs physical checking. The electronic switch-off and capture
start share a scheduled boundary; software does not claim the physical motor stops rotating instantly.
No startup test buzz. A fist released before 2 seconds cancels the pending capture.
If the mic is not ready by the first-buzz deadline, the glove cancels without buzzing.

OPEN THESE IN ARDUINO IDE:
  GloveDemo/GloveDemo.ino -> glove FireBeetle ESP32 (DFR0478)
  MicDemo/MicDemo.ino     -> mic/collar FireBeetle ESP32 (DFR0478)
Board: FireBeetle-ESP32 (esp32:esp32:firebeetle32).
Developed against Arduino ESP32 core 3.3.11, ArduinoJson 7.4.3.
Install ArduinoJson 7.x with Library Manager if missing. No PubSubClient/CollarMqtt install is needed here.
Serial Monitor: 115200. Initial clock/network acquisition may take several seconds.

WAITING FOR COMMS SETTINGS:
  demo_settings.local.json holds Wi-Fi, role credentials, endpoint, session and certificate path.
  certs/ca.crt must contain the repaired PUBLIC CA certificate.
  Run CONFIGURE_DEMO.bat after settings/shared-header edits, then upload BOTH sketches.
  Generated DemoConfig.h files intentionally compile with missing settings, but refuse to connect or capture.
  The default target is 140.245.52.118:8883 with certificate verification. No insecure TLS bypass.
  The example config contains no working passwords or CA. Local config/generated credential headers are gitignored.
  A plaintext local-test mode exists only with an explicit flag; it is disabled by default.

WIRING (unchanged):
  Glove flex: thumb GPIO35, index GPIO34, middle GPIO39; 12-bit ADC, 47k resistor dividers.
  MPU6050 SDA GPIO21, SCL GPIO22, address 0x68, 100kHz I2C.
  Haptic module IN -> D2/GPIO25, VCC -> board VCC, GND -> GND.
  INMP441 BCLK GPIO14, WS GPIO17, SD GPIO16, VDD 3V3, GND and L/R GND (left channel).

FINGER STATES:
  Firmware continuously calculates states, including between recordings:
  thumb bend >=1369, release <=1353
  index bend >=1596, release <=1533
  middle bend >=3435, release <=3420
  Model features are 0=NOT_BENT, 1=BENT. Raw ADC does not enter the transmitted feature tensor.
  The FULL-fist trigger separately requires thumb >=1676, index >=1884, middle >=3480 for 2 seconds.
  This avoids using the loose throwing grip as the intended fist trigger.
  All three bend values must increase with bending, matching the user's measured wiring.

SYNCHRONISATION:
  Both devices use bounded-delay SNTP queries and map UTC to their local monotonic clocks.
  Default NTP sources: time.cloudflare.com, time.google.com, pool.ntp.org. Configurable.
  Default maximum estimated clock error is 50ms PER DEVICE; independent clock error can accumulate.
  A capture is scheduled 3 seconds after the fist begins: 2-second hold + 1-second buzz.
  The mic acknowledges readiness before the glove commits to the first buzz.
  Mappings are frozen during a capture; clocks are not stepped while active.
  The mic maps DMA completion timestamps/sample indices into the requested interval, selecting exactly 48,000 samples.
  IRQ/DMA mapping jitter is checked and included in metadata; exact physical alignment still needs measurement.
  Estimated network-time bounds are not a claim of sample-accurate cross-device synchronisation.

OUTPUTS:
  hand/clips: one JSON frame, 150 x 9, 50Hz, physical SI IMU plus three binary states.
  mic/clips: one binary MLW1 envelope containing JSON metadata plus a COMPLETE 96,044-byte WAV.
  WAV: 3 seconds, 16kHz mono, signed 16-bit little-endian PCM; real RIFF/WAVE header is generated on ESP32 in RAM.
  No SD card/filesystem or external PSRAM is assumed. The WAV stays frozen until upload/deadline.
  Whole-message QoS1 streaming avoids allocating a second full audio-sized MQTT outbox copy.
  A broker PUBACK proves broker acknowledgement, not AI inference or visualisation completion.
  One capture at a time, finite queues, no continuous waveform/sensor upload, no artificial padding.
  Missing samples, IMU errors/clipping or audio gaps fail the capture rather than silently repairing it.

FOR YOUR COMMS/AI TEAM:
  Read PROTOCOL_DEMO.txt before adapting the receiver. This intentionally differs from the old v1 draft:
  three BINARY fingers, 150x9, explicit fist/cue scheduling, and WAV instead of the MLA1/raw-PCM profile.
  The existing 100x9 two-second model input is NOT silently cropped/resampled by this hardware code.
  Topics share milo/v1/<session>/. Both devices use the same capture_id.
  Glove role MUST read mic/results (not optional for this demo).
  This code does not claim the receiver, live ACLs, network path, trained AI or Unity are already implemented.

OPTIONAL LOCAL RECEIVER:
  Run SETUP_MONITOR.bat once if paho-mqtt is missing.
  START_MONITOR.bat asks for the monitor MQTT password and saves real received pairs under received/<capture_id>/.
  It writes voice.wav, glove.csv and both metadata JSONs, and never sends simulated AI actions.
  The monitor account needs read access to the demo session topics.
  tools/wire_fixtures.py generates clearly marked SIMULATED protocol samples for receiver development.
  tools/test_demo.py checks payload integrity, pairing, duplicates and rejection of old/corrupt formats.

REJECTION HAPTICS:
  hand/feedback supports the earlier haptic-long-v1 outcomes: one 500ms vibration for VOICE_REJECTED,
  two 500ms vibrations separated by 250ms for GESTURE_REJECTED. They are deferred while recording/buzzing,
  checked for target/capture/expiry and deduplicated. Triggering is suppressed during them and for 700ms after.
  Their shorter patterns are separate from the two 1-second capture cues.

Source references used:
  https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
  https://www.rfc-editor.org/rfc/rfc4330
  https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html
  The actual installed ESP32 3.3.11 driver headers and existing tested collar/glove acquisition code.
