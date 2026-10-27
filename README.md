# Milo â€” Wearable hardware, firmware and collection tools

CG4002 Group B12 hardware sources, updated through 27 October 2026.

This repository contains the glove and microphone ESP32 firmware, 3D printed housing designs, calibration tools, wireless collectors, hardware tests and development history. It packages the hardware work; the team's complete Ultra96 inference and Unity visualiser projects are maintained separately.

## Where to start

| Folder | Contents |
| --- | --- |
| `firmware/demo_latest/` | Current paired glove/mic demo; all three glove flex sensors enabled |
| `collectors/glove_latest/` | Three-finger gesture collection; three-second, 150-frame clips; updated calibration |
| `collectors/voice_latest/` | Standalone fast voice collector using a laptop MQTT broker |
| `calibration/usb_flex/` | USB-only relaxed/fist calibration; no MQTT or microphone needed |
| `calibration/reference_20261023/` | Raw measurements, summary and thresholds used by the latest firmware |
| `tests/` | Flex/IMU checks, wireless baseline, motion stress and range retest tools |
| `cad/` | STL variants, concepts, print notes, generator scripts and MakerBot jobs |
| `docs/architecture/` | Editable system diagram and two image previews |
| `firmware/history/`, `collectors/history/` | Earlier snapshots, including the temporary two-finger demo |
| `collectors/candidate_data/` | Fast USB/Wi-Fi continuous recording and gesture/background annotation |
| `prototypes/candidate_detector_latest/` | Latest glove-only automatic action proposal model (v2) and live validation UI |
| `prototypes/history/candidate_detector_v1/` | First local detector and its training tools |
| `collectors/wrong_actions/` | Unlimited, variable-length deliberate wrong-action takes; manual next gesture |

## Current demo flow

1. Both ESPs connect to Wi-Fi and the shared MQTT service using verified TLS. The glove waits for a live, compatible microphone readiness heartbeat.
2. Hold a fist with **thumb, index and middle bent for two seconds**. The glove sends a capture preparation request through MQTT, and the mic acknowledges that its recording task is armed.
3. The glove vibrates for one second. When it stops, perform the gesture and speak.
4. Both ESPs capture the same scheduled three-second window with a common capture ID. The motor is off during recording.
5. A one-second finishing vibration occurs, then both recordings upload. Release the full-fist condition for at least 200 ms before another capture; every finger need not become completely straight.

The glove sends 150 rows of `[ax, ay, az, gx, gy, gz, thumb, index, middle]`. Acceleration is m/sÂ² including gravity; gyro is rad/s; finger states are 0=NOT_BENT and 1=BENT. The mic sends an MLW1 binary envelope containing metadata JSON and a complete three-second, 16 kHz mono PCM16 WAV. See `firmware/demo_latest/AI_PAYLOAD_GUIDE.txt`, `PROTOCOL_DEMO.txt` and `MQTT_TOPICS.txt`.

No gesture or voice inference runs on the ESPs in this paired demo. The separate glove-only prototype below runs a local candidate model; it has not yet replaced the paired demo's fist trigger. The Linux TLS relay forwards MQTT traffic to the broker; glove/mic control messages also travel through MQTT.

## Current calibration: 23 October

Calibration ID: `nitin-20261023-usb-relaxed-fist-v3`.

| Finger | GPIO | BENT at or above | NOT_BENT at or below |
| --- | ---: | ---: | ---: |
| Thumb | 35 | 1696 | 1583 |
| Index | 34 | 1920 | 1762 |
| Middle | 39 | 3520 | 3487 |

Between thresholds, the previous state is retained. The three-finger trigger minima match the bend thresholds. The middle sensor is read normally and is no longer forced to zero. The values separated all 240 recorded relaxed/fist readings in three repeated rounds. Partial bends, ball grip and motion reliability were not newly calibrated by that static test.

The latest gesture collector uses matching thresholds and a new hardware profile (`...binary_flex_v6`) to distinguish new sessions from older calibration. Existing datasets and historical firmware retain their original thresholds and labels. The IMU reference bias is historical and was not recalibrated in this USB flex test.

## Flash the paired demo

Board: **FireBeetle-ESP32 / DFR0478** (`esp32:esp32:firebeetle32`). The development build used Arduino ESP32 core 3.3.11 and ArduinoJson 7.4.3. See component requirements for Python monitoring tools.

1. In `firmware/demo_latest`, copy `demo_settings.example.json` to `demo_settings.local.json`.
2. Fill in your Wi-Fi and the privately supplied MQTT role passwords. Keep the intended TLS settings and public CA file. Private credentials are deliberately absent from this package.
3. Run `CONFIGURE_DEMO.bat`. This generates the two `DemoConfig.h` files and synchronizes shared support headers.
4. Open `GloveDemo/GloveDemo.ino` and upload to the glove. Open `MicDemo/MicDemo.ino` and upload to the mic when needed.

**Only the glove requires reflashing for the 23 October threshold/three-finger change.** An already working mic using the same network, session and protocol can keep its existing firmware. Changes to network/session settings may require reflashing both devices.

Packaged `DemoConfig.h` files are sanitized build examples, not working private connection settings. They are ignored by Git; generate them locally before uploading. The updated trigger logic lives in `GloveDemo/GloveApp.h`; the configuration step only synchronizes common support headers and does not undo it.

## Collect new data

### Glove

Use `collectors/glove_latest`. Set the Wi-Fi settings and laptop broker IP near the top of `MBF_v1/MBF_v1.ino`, then flash it. This collector needs PubSubClient 2.8. Run `SETUP_ONCE.bat`, then `START_COLLECTION.bat`. It collects ten accepted takes per gesture sequentially, with three binary finger states and six IMU axes. Each clip is three seconds, including one second of preparation. Use a **new session** with this calibration/profile.

The model export has 150 Ã— 9 features. `X` applies session gyro-bias correction; `X_raw` retains the uncorrected physical IMU representation used by the demo. Match preprocessing at training and inference. Review throw samples because a loose ball grip differs from a fist.

### Voice

Use `collectors/voice_latest`. Copy `voice_settings.example.json` to `voice_settings.local.json`, enter the laptop broker and Wi-Fi settings, then run `CONFIGURE_VOICE.bat` and flash `MicVoiceFast/MicVoiceFast.ino`. Run `SETUP_ONCE.bat` and `START_VOICE_COLLECTION.bat`. The glove can remain off. This uses the local laptop broker, not the remote TLS demo endpoint.

The voice tool records three-second WAV takes without a preparation countdown or forced playback. The original tool defaults to speaker Nitin; identify the actual speaker correctly when collecting another person's recordings.

Glove and standalone voice datasets are separate collections, not synchronized gesture/audio pairs.

## Automatic action detection prototype

Start with `prototypes/candidate_detector_latest/README_FIRST.txt`. Flash its `GloveCandidateDetector/GloveCandidateDetector.ino`, then launch `START_V2_LIVE_TEST.bat`. It supports USB and Wi-Fi; Wi-Fi credentials are configured over USB and stored on the ESP. There is no fist trigger or microphone dependency.

The ESP evaluates a small random forest on rolling 0.8-second sensor windows every 0.1 seconds. Candidate proposals request a three-second clip (one second before the proposal, two seconds after). The laptop receives continuous samples and extracts the clips; this prototype does not yet synchronize retrospective microphone recordings or send clips to Ultra96. Overlapping proposals remain available, while the UI groups them for display.

The latest v2 model reduces the excessive everyday-motion proposals seen in v1. It uses IMU, binary finger states and relative raw-flex changes locally. Raw ADC values are local trigger features; the downstream gesture payload remains six IMU axes plus three binary states. Model weights, generated C++ headers, training code and evaluation reports are included. Development results are not independent evidence of 99% recall; real actions can still be missed.

Retraining needs the separately stored recordings and derived training arrays. In particular, v2's `training/retrain_hard_negatives.py` needs v1's local `training_windows.npz` and `window_scores.csv` plus the hard-negative ZIP. These are intentionally not committed. Historical scripts retain original workstation paths; adapt paths before reproducing exports or training elsewhere.

## Wrong-action data and labels

Use `collectors/wrong_actions/START_WRONG_COLLECTION.bat`. Existing MILO1/MILO2/MILO3 glove logger/detector firmware is supported; reflashing is normally unnecessary. Press Space before and after each attempt, collect as many takes as wanted, and use Next command manually. Clips keep their actual duration, without three-second padding.

Each CSV includes all six IMU axes and all three binary finger states. Intended command and mistake notes are in metadata. A deliberately wrong attempt is incorrect for its intended command; it can still resemble another valid command. Such intentional attempts are not automatically negative examples for the local action detector. Review the observed gesture metadata when assigning final classifier labels. Everyday/background recordings are a separate data source.

## Repository contents and local data

Source code, CAD models, calibration references, trained trigger weights, documentation and firmware history are versioned. Recorded voice/gesture datasets, derived training arrays, private settings and generated build output stay local and are ignored by Git. Original collection folders and recordings are preserved separately; this repository contains no recording ZIPs.

Small USB calibration references are included because they define the current thresholds. Earlier snapshots have private credentials sanitized and local settings converted to examples. Generate private connection headers locally using the corresponding configuration tools. Do not commit Wi-Fi or MQTT passwords.

Component validation notes describe the checks performed when each tool was developed. `docs/REPOSITORY_VALIDATION.json` records source checks for this snapshot. No new hardware test or reflash was performed while preparing the repository.

No open-source license has been selected. Keep the repository private unless the team agrees on publication and licensing.
