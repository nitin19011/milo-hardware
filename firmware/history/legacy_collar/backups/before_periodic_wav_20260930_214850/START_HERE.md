# Collar microphone: full-WAV MQTT — 16 Sep 2026

## What changed

The collar now records a complete candidate clip, then publishes **one binary WAV per MQTT message**. Your teammate does not join audio chunks or add a WAV header. The old chunked PCM protocol is replaced, not used alongside this one.

Current broker address and home Wi-Fi credentials in Collar_Mic.ino were preserved. Glove firmware, the globally installed PubSubClient library, the recorder sketch, your recordings, command dataset and trained-model header were not changed. Previous firmware/receiver/docs are backed up under `backups/before_full_wav_2026-09-16`.

## Hardware and firmware

Use the same DFR0478 collar board: INMP441 VDD -> 3V3; GND and L/R -> GND; SCK -> GPIO14; WS -> GPIO17; SD -> GPIO16. Disconnect USB and battery before changing wiring. Nothing connects from collar to glove.

Open `Collar_Mic/Collar_Mic.ino`. All project-local firmware code and model data are now embedded in this single sketch. Its embedded CollarMqtt implementation is a derivative of PubSubClient with a corrected large outgoing-message length; keep that correction for whole-WAV publishing. Standard Arduino/ESP32 libraries are still required. Licensing/change notes are embedded in the sketch and retained in `Collar_Mic/THIRD_PARTY.md`.

Use your existing Arduino-ESP32 3.3.11 / FireBeetle board selection. Serial Monitor speed is 115200. Recheck the broker PC's Ethernet IPv4 if it changes; the ESP must not use 127.0.0.1. Both devices connect directly to the same Mosquitto broker.

## Recording limits and memory

- Rolling history: 1.4 seconds BEFORE detection, including the start of Milo.
- Following audio: up to 2.6 seconds AFTER detection.
- End early after 0.6 seconds below the simple quiet threshold.
- Maximum WAV: four seconds, mono 16 kHz, signed 16-bit PCM, 128,044 bytes including its 44-byte header.

These are starting limits, not a guarantee that every phrase fits. A long pause after Milo can end capture early; a noisy room can force the duration cap. Metadata flags clips that reach the cap as `truncated`. Check playback for missing words.

Audio storage is 128 kB across four 32 kB blocks. The idle rolling history uses the SAME memory as the final recording. Publishing writes from those blocks into one MQTT message; it does not allocate a second WAV-sized MQTT buffer. Internal TCP writes are NOT separate MQTT messages.

There is room for only one candidate clip at a time. The mic task keeps draining I2S and calculating levels while that buffer is waiting/sending, but wake-word matching pauses until it is released. Back-to-back commands during upload can therefore be missed. `busy_ms` is cumulative time spent in that busy state; Serial prints `upload_ms` per sent clip. Measure this on the real board/network. The network task avoids interleaving other MQTT messages within a WAV transfer and aborts on write failure or its between-writes time budget. Individual socket writes can still add timeout latency.

No audio is published while idle/untrained. Captures spanning a detected I2S read gap or observed connection loss are discarded. Completed offline/stale clips are not replayed automatically. QoS is still 0: a successful socket write is NOT an AI acknowledgement, and clips can be lost on failure. There is no retry/offline storage. Raising the duration limit requires reviewing memory, sender bounds, receiver bounds and tests together.

## First bench check

Upload Collar_Mic to the collar. Confirm:
- Startup has no audio-storage allocation error.
- Wi-Fi and MQTT connect.
- RMS/peak respond to speech.
- Free heap is reported at startup and after connection. Watch for resets or memory failures.
- `read_gaps`, `compute_overruns` and `aborted_clips` do not increase in a normal quiet-network test.

The current sketch contains the previously enrolled Milo model. Normal microphone-level packets are periodic; WAV messages depend on the detector triggering. Embedding the model has not changed its detection accuracy.

## Collect and prepare Milo references

This is separate from the 60 labelled command recordings for your AI teammate. Keep those under command_dataset; do not relabel whole command recordings as Milo-only templates.

Upload `Collar_Recorder/Collar_Recorder.ino` to the collar, then CLOSE Serial Monitor. It temporarily replaces normal MQTT firmware and records over USB. In a terminal inside Collar_System:

```bat
py -m pip install -r requirements.txt
py milo.py record --port COM5 --group templates --count 8
```

Use the actual COM port. Wear the mic at the collar. For each three-second take: press Enter, stay quiet for 0.3 seconds, say **Milo alone once**, and let the recording finish. Listen to the WAVs in recordings/templates. Use natural variations; replace bad takes. This command adds eight takes, rather than resuming to eight; if you already have templates, count the existing good ones first. Training accepts 6–12 templates.

With Collar_Recorder still uploaded:

```bat
py milo.py record --port COM5 --group cal_positive --count 8
py milo.py record --port COM5 --group cal_negative --count 8
py milo.py train
py milo.py record --port COM5 --group test_positive --count 10
py milo.py record --port COM5 --group test_negative --count 10
py milo.py evaluate
```

Positive clips: natural Milo + command, e.g. Milo sit, Milo fetch, Milo bang. Negative clips: speech WITHOUT Milo, similar words, room noise and clothing rustle. Real conversation containing Milo is wake-positive even if it is not a command. Keep the first 0.3 seconds quiet in each recording. Test recordings must be fresh, not copies of development data.

This remains the small acoustic-template/DTW prototype, not a neural network or command classifier. Training runs on the laptop and replaces only the section between `// BEGIN MILO MODEL` and `// END MILO MODEL` in `Collar_Mic/Collar_Mic.ino`; leave those markers intact. Upload **Collar_Mic again** to put those references into flash. The ESP compares sound against Milo references; the downstream AI decides which command, if any, was spoken. Some accidental triggers and missed commands remain possible. Do not claim calibration results as independent accuracy.

## Receive the complete WAV on the broker PC

Start your existing broker. Open a terminal inside Collar_System:

```bat
py receive_clips.py --host YOUR_BROKER_PC_IPV4
```

Use the same working address as MQTTX. The host is now required explicitly, so this script will not silently connect to the old laptop address. The output folder defaults to `received_wavs`.

The receiver subscribes to `sensor/collar/voice/wav/#` and the optional event topic. Each voice message already contains a complete WAV: the script validates the expected header/length and saves the payload unchanged as `<session>_<clip>.wav`. Optional metadata becomes a matching JSON file if received after the WAV. No assembly, format conversion or base64 decoding is needed. Duplicate identical clip IDs are ignored; conflicting data with the same ID is rejected.

In MQTTX subscribe to `sensor/collar/voice/#`. WAV payloads are binary, not readable JSON and not automatically playable there. Use the saved WAVs to listen. Test at least several short and slower phrases, then 30–50 fresh varied commands and normal conversation; verify trigger recall, false triggers, complete phrases, upload latency and behavior after network loss.

## Topic changes for the AI team

- `sensor/collar/voice/wav/<session>/<clip_id>`: **one whole binary RIFF/WAV payload**, no JSON prefix/envelope.
- `sensor/collar/voice/event`: optional schema-version-2 JSON, published after the WAV; contains its exact wav_topic, model ID, timestamp, duration, byte count and truncated flag. A WAV is usable without this metadata, but absence of metadata does not prove it was not truncated.
- Old `sensor/collar/voice/audio` chunks and `wake_candidate` start messages are no longer emitted.
- `sensor/collar/microphone` still reports levels and diagnostics, approximately 5 Hz when network work is available.
- `status/collar/connection` still reports retained ONLINE/last-will OFFLINE.
- Glove topics remain unchanged.

The topic session ID is eight hexadecimal digits, and clip ID is a positive decimal sequence. IDs are not command labels. Both WAV and event are non-retained. Timestamp is collar boot-relative microseconds; it is not synchronized with the glove's clock. Different-board synchronization and AI/FPGA input preprocessing remain downstream work.

The broker and subscriber must allow at least 128,044 payload bytes plus MQTT overhead. This is not a request to expose the broker to the internet; keep anonymous development MQTT on the private home network only.

## Tests and rollback

Run `py test_tools.py` for the updated receiver/matcher tests and `py test_command_collector.py` for dataset-collector checks. Synthetic test files go to test_output, not real recordings. See VALIDATION.md for the native C++ checks and build limitations.

The previous files are in `backups/before_full_wav_2026-09-16`. Back up any newer edits before restoring them. Restoring the old sketch also requires restoring the old receiver because the audio protocols differ. File changes do not change a board until firmware is uploaded.
