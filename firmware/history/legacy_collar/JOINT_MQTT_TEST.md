# Glove + collar MQTT check and flex calibration

## What this checks

Both ESP32 boards connect independently to the same Mosquitto broker. They do
not pair directly with each other. MQTTX can subscribe to both at once. The
microphone remains on the collar, not the glove.

Current matching settings in both operational sketches: Wi-Fi `HUAWEI-cU9R`,
broker `192.168.101.8`, port `1883`. The PC may use Ethernet on the same LAN.
If its Ethernet IPv4 has changed, update `MQTT_BROKER_IP` in BOTH sketches and
re-upload. The broker address is never the ESP32's own IP address.

## Upload and subscribe

1. Upload `MBF_v1/MBF_v1.ino` to the GLOVE FireBeetle. Its new `FlexState.h`
   must remain in that sketch folder; Arduino loads it automatically.
2. Upload the existing `Collar_System/Collar_Mic/Collar_Mic.ino` to the COLLAR
   FireBeetle. `Collar_Recorder` is USB-only and does NOT publish MQTT.
3. Check each board's serial monitor separately at 115200 baud for Wi-Fi and
   MQTT connected messages. Identify each board's COM port; they cannot both
   use the same COM port simultaneously.
4. Start the existing private-network Mosquitto broker/listener.
5. Connect MQTTX to `mqtt://192.168.101.8`, port 1883, without TLS or credentials
   for the current anonymous development listener. Use its auto-generated
   client ID; do not reuse either ESP32's client ID.
6. Subscribe to `sensor/glove/#`, `sensor/collar/microphone`, and
   `status/+/connection`. These show JSON telemetry without binary WAV traffic.

Expected topics:

| Topic | What to check |
|---|---|
| `sensor/glove/gesture` | Approximately 50 packets/s: IMU, finger states, raw flex readings |
| `sensor/collar/microphone` | Approximately 5 packets/s: RMS, peak, validity and existing diagnostics |
| `status/glove/connection` | Retained `ONLINE`, with a last-will `OFFLINE` after unexpected disconnect |
| `status/collar/connection` | Same for the collar |

Move the glove while speaking near the collar. Confirm glove motion/raw values
and collar RMS/peak respond at the same time. Receiving RMS/peak does NOT prove
that a usable voice WAV was delivered. Voice triggering is deferred: the
existing collar's unreliable Milo logic was not changed in this update.

If testing an existing WAV send, the whole binary WAV uses
`sensor/collar/voice/wav/<session>/<clip>`; `receive_clips.py` saves it for
playback. A binary WAV is not JSON. Until triggering is replaced or a separate
manual test is agreed, do not rely on speaking Milo to produce a clip.

## Flex wiring and calibration

| Finger | GPIO | Board analog label | Initial threshold |
|---|---:|---|---:|
| Thumb | 35 | A3 | 1800 (placeholder) |
| Index | 34 | A2 | 1800 (placeholder) |
| Middle | 39 | A1 | 1800 (placeholder) |

No battery ADC monitoring or microphone code was added to the glove. MPU-6050
remains on SDA21/SCL22. Calibrate with the flex sensors mounted in their intended
positions and without changing divider wiring partway through.

For EACH finger:

1. Hold it straight for 5 seconds. Record the raw minimum and maximum.
2. Bend it to the minimum bend that should count as BENT; hold for 5 seconds.
   Record the raw minimum and maximum. Repeat opening/bending a few times.
3. Verify that only the intended finger's reading changes strongly. If a channel
   stays at 0 or 4095, check wiring/measurement range before choosing a threshold.
4. Set the corresponding `FLEX_*_BENT_THRESHOLD` in the glove sketch.
   For rising readings with separated ranges, a starting threshold is halfway
   between the largest straight reading and the smallest bent reading. For
   falling readings, use halfway between the smallest straight reading and the
   largest bent reading and set that finger's `FLEX_*_BEND_INCREASES=false`.
   If the ranges overlap, a single threshold will not reliably separate them.
5. Re-upload and check straight, each finger individually, and all three bent.

Example only: straight 1200–1300 and intended bent 1700–1900 gives an initial
threshold of 1500. This is NOT your measured calibration.

A 20-count release margin reduces flickering: with rising readings and threshold
1800, the state enters BENT at 1800 or above and returns to NOT_BENT below 1780.
For falling readings it enters at 1800 or below and releases above 1820.
Threshold equality counts as bent. The raw reading is an ADC count, not an angle.

The existing JSON `flex` object remains compatible:

```json
"flex": {"thumb":"BENT", "index":"NOT_BENT", "middle":"BENT"},
"flex_raw": {"thumb":1900, "index":1200, "middle":1950}
```

The example is a fragment of the packet. Raw MQTT output is controlled by
`PUBLISH_FLEX_RAW`; set false after calibration if not needed. State output
continues regardless. Serial shows all three raw readings and states at 5 Hz.

## Interpretation and limitations

- `seq` is independent for each board, not a shared counter. Timestamps are
  each board's time since boot, NOT synchronized wall-clock time. Concurrent
  arrival is not precise motion/audio synchronization for AI fusion.
- Telemetry uses QoS 0 and is not retained. A fresh stream is stronger evidence
  of a live board than an old retained ONLINE status. Offline summaries are not
  replayed as fresh readings.
- The glove's existing IMU `valid` flag is NOT a reliable I2C transport check
  with the installed Adafruit library. This change did not repair the previously
  reported IMU spikes or hardware faults. Verify sensible stationary readings.
- Software checks passed for flex hysteresis, finger labels and actual JSON
  serializer with/without raw readings, including packet bounds. ESP32 source/
  object compilation passed for the glove. No hardware was flashed or tested
  by the assistant, and no full linked firmware build is claimed.

Backups: glove `.ino.bak` beside its sketch and collar source copies under
`backups/before_joint_test_20260916_181721/`. Collar code was left unchanged.
