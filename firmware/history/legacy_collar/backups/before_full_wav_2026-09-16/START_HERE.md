# Separate collar microphone — 16 Sep 2026

Both boards are DFR0478 FireBeetle ESP32s. The glove now handles MPU6050 and three flex sensors; the collar handles INMP441 audio. Each connects independently over Wi-Fi to the same Mosquitto broker on your laptop. The collar does NOT send audio through the glove, and there is no wire between them. The laptop/AI subscribes to both devices.

## What changed

- `../MBF_v1/MBF_v1.ino` is now glove-only: microphone/I2S initialization, mic task, queue and mic publishing were removed. Existing motion/flex pins, thresholds, 50 Hz sampling, Wi-Fi settings and MQTT motion format remain unchanged. Battery monitoring remains absent.
- Its exact previous version is saved as `../MBF_v1/MBF_v1.before_collar_2026-09-16.ino.bak`. The `.bak` extension prevents Arduino compiling it as another sketch.
- `Collar_Mic/Collar_Mic.ino` is the normal collar firmware: local mic capture, Serial RMS/peak output, MQTT levels and connection status, plus the optional existing Milo-template detector.
- `Collar_Recorder/Collar_Recorder.ino` is temporary USB recording firmware for listening tests and enrollment. Uploading it replaces the normal collar firmware until you upload Collar_Mic again. It has no Wi-Fi/MQTT.
- `milo.py`, `receive_clips.py` and the detector headers were adapted for the collar. The older `outputs/milo_prototype` package is unchanged historical work; do not upload its combined glove/mic sketch for this split arrangement.

## Wire the collar, with both USB and battery disconnected

Use short wires local to the collar board. These are GPIO numbers, not header-position numbers.

| INMP441 pin | Collar FireBeetle connection |
|---|---|
| VDD | 3V3 — never 5 V |
| GND | GND |
| L/R | GND, selecting the left channel |
| SCK | GPIO14 |
| WS | GPIO17 |
| SD | GPIO16 |

Remove the mic connections from the glove. Its MPU remains SDA21/SCL22; flex inputs remain thumb39, index34, middle35. Each board needs its own power source; use USB for initial bench testing. Any later battery must suit the board's battery input and connector polarity—do not put a Li-Po directly onto the 3V3 pin. Insulate the collar assembly from skin/metal and keep the microphone opening clear of clothing.

## First test: collar only, no training needed

1. Connect only the collar ESP to USB so there is no ambiguity about the upload port.
2. Open `Collar_Mic/Collar_Mic.ino` in Arduino IDE. Keep all its `.h` files in the same folder. Use your existing FireBeetle board selection and Arduino-ESP32 3.3.11 setup. PubSubClient is required; ESP_I2S and WiFi come with the board package. Do not mix in the legacy `driver/i2s.h` driver.
3. Check `WIFI_SSID`, `WIFI_PASSWORD` and `MQTT_BROKER_IP` at the top. The existing values are preserved, but `172.20.10.2` is only correct if it is still your laptop's Wi-Fi IPv4. Check with `ipconfig`. Both boards must use the same actual broker address and accessible Wi-Fi network. Use a private network; no internet port forwarding for anonymous MQTT.
4. Upload and open Serial Monitor at **115200**. You should see `Collar microphone ready`, then a line approximately every second containing `mic rms=... peak=...`. Speaking near the collar should increase the readings. Persistent zeros, clipping near 32768, resets, or steadily increasing `read_gaps` need investigation before training. RMS/peak are signal levels, not speech recognition; `valid` only describes successful frame acquisition.
5. Start your existing Mosquitto broker. In MQTTX connect to that broker and subscribe to `sensor/collar/#` and `status/collar/connection`. Microphone-level packets should arrive about five times per second.
6. Upload the updated MBF_v1 to the glove board. Power both boards. Check glove flex/IMU packets and collar level packets arrive together; each should also work while the other is powered off.

The collar has separate audio and network FreeRTOS tasks. MQTT reconnects do not intentionally stop mic capture. Distinct client IDs and `source_id` values prevent the glove and collar from replacing each other's broker connection. The collar's level gain is 4, matching its recorder; its numbers will therefore differ from the old ungained MBF_v1 level values.

## MQTT topics

| Device | Topic | Contents |
|---|---|---|
| Glove | `sensor/glove/gesture` | Existing IMU + BENT/NOT_BENT flex packets, nominally 50 Hz |
| Glove | `status/glove/connection` | Retained ONLINE / last-will OFFLINE |
| Collar | `sensor/collar/microphone` | RMS, peak, acquisition validity and detector diagnostics, approximately 5 Hz |
| Collar | `status/collar/connection` | Retained ONLINE / last-will OFFLINE |
| Collar | `sensor/collar/voice/event` | Candidate clip start/end metadata, only after detector enrollment |
| Collar | `sensor/collar/voice/audio` | Candidate PCM audio chunks, only after detector enrollment |

Audio and events are not retained. The glove no longer publishes `sensor/glove/microphone`. Old messages may remain visible in MQTTX history; that does not mean the new glove is publishing them.

Each ESP's `timestamp_us` is its OWN time since boot. Do not subtract a collar timestamp from a glove timestamp to align gestures and voice. For basic testing the laptop can label arrival times; precise multimodal synchronization still needs a separate clock-alignment design. No AI fusion or command execution is implemented in this change.

## Listen to collar recordings

Upload Collar_Recorder to the collar board, then close Serial Monitor. Open a terminal in **this Collar_System folder**:

```bat
py -m pip install -r requirements.txt
py milo.py record --port COM5 --group templates --count 8
```

Use the collar board's actual COM port, not necessarily COM5. This records through your INMP441, not your laptop mic. For each three-second take, wait quietly for the first 0.3 seconds, then say **Milo once**. Recorded WAVs appear in `recordings/templates`; double-click them to check clarity. Wear/place the microphone where it will actually sit for the demo. Redo bad recordings rather than training on clothing rustle or clipped audio. The first eight recordings also become your templates if you continue below.

## Optional: enable the local Milo detector

**The supplied model is untrained. Initially you get levels, not voice clips or recognized words.** Loud sound alone does not trigger MQTT audio. No continuous raw audio is sent during normal idle operation.

The existing detector is a small, speaker-specific acoustic-template/DTW prototype, not a neural network or intent classifier. It compares sound with your examples of Milo. It cannot distinguish “Milo sit” from conversation mentioning Milo, and it cannot guarantee every command is detected. The downstream AI must reject noncommands. Moving the mic from glove to collar changes its sound, so collect fresh collar recordings instead of relying on old glove calibration.

With Collar_Recorder still uploaded, collect the following:

```bat
py milo.py record --port COM5 --group cal_positive --count 8
py milo.py record --port COM5 --group cal_negative --count 8
py milo.py train
py milo.py record --port COM5 --group test_positive --count 10
py milo.py record --port COM5 --group test_negative --count 10
py milo.py evaluate
```

Positive examples: natural “Milo sit”, “Milo come”, “Milo fetch”, without a deliberate pause after the name. Negative examples: speech WITHOUT Milo, similar-sounding words, and realistic background/clothing noise. Actual conversation containing Milo is wake-positive, even if the AI should later reject it as a command. Start every recording with 0.3 seconds of quiet and finish within three seconds. Use fresh test recordings, not copies of training examples. Calibration results are not independent accuracy.

Training produces `Collar_Mic/milo_model.h`, plus `model.json` and a calibration report. Upload **Collar_Mic again** to compile those references into the ESP's flash. Training is done on the laptop; matching runs on the ESP. The board does not train itself or receive the model over MQTT.

The detector maintains 1.4 seconds of recent audio locally. A possible match sends that history and following audio, ending on 0.6 seconds of quiet or a 2.6-second post-trigger cap. That supports “Milo sit” without a button, gesture, or wait-for-beep step. Maximum clip length is approximately four seconds. A second command during a clip can be included in that clip rather than triggering separately.

Start the laptop receiver BEFORE speaking:

```bat
py receive_clips.py --host 172.20.10.2
```

Use your broker's actual address; `127.0.0.1` works when running on the broker laptop with a local listener. Complete clips are saved as WAV + JSON in `received_clips`. MQTTX shows event JSON, but does not reconstruct/play the binary audio. Check that saved clips include the whole command. Try varied volume/room noise and at least 30–50 fresh commands before trusting recognition.

For the AI team: audio packets contain ASCII `MLA1`, then four little-endian uint32 fields (session ID, clip ID, zero-based chunk index, sample count=320), then 640 bytes of mono 16 kHz signed int16 little-endian PCM. Final metadata gives frame count, CRC32 of PCM, `complete` and `truncated`. `receive_clips.py` is the reference assembler. Distances are matching errors, NOT confidence percentages.

QoS 0 means delivery is not guaranteed. Missing/corrupt clips are rejected, not retransmitted. `complete:true` is a sender-side flag, not proof of delivery; a CRC-checked `truncated:true` clip can still be missing the end of speech. Queue drops, read gaps and compute overruns should stay zero. These counters do not detect every possible DMA timing problem. Real speech accuracy, memory headroom and real-time performance require physical-board testing.

## Existing issues deliberately not changed

The earlier index flex value stuck at 4095 and abnormal MPU readings are not fixed by moving the microphone. Inspect/test those separately. The installed Adafruit MPU6050 library's `getEvent()` returns true unconditionally, so the retained glove `imu.valid` field is not a reliable I2C failure check. Only the misleading code comment was corrected; no new sensor algorithm was slipped into this hardware split.

## Reverting

The backup ending `.ino.bak` contains the original combined glove/mic sketch. To restore it, first save your newer glove sketch, then copy the backup contents back into MBF_v1.ino and upload it. Reverting files alone does not change firmware already on a board. Use the old combined firmware only with its matching physical wiring.

See `VALIDATION.md` for the checks completed here and what still needs Arduino IDE/hardware verification.
