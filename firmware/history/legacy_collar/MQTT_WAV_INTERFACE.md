# Collar audio interface for the AI teammate

Subscribe to `sensor/collar/voice/wav/#` on the project Mosquitto broker.
Each message's payload is **one complete WAV file**, including its RIFF header.
Save `message.payload` as a `.wav` file or pass those bytes directly to a WAV decoder.
Do not decode as text/JSON/base64 and do not join multiple messages.

Format: PCM, mono, 16,000 samples/second, signed 16-bit little-endian audio.
Maximum duration: 4 seconds. Maximum payload: 128,044 bytes.
Topic example: `sensor/collar/voice/wav/1234abcd/7` (session ID / clip ID).

The microphone continuously listens locally; WAVs are published only after a possible
Milo match and completion of its candidate clip. This is NOT proof of a valid command.
The downstream AI must identify/reject the utterance. Transmission is QoS 0,
non-retained, with no automatic retry. The subscriber must be online beforehand.

Optional `sensor/collar/voice/event` JSON follows the WAV, with schema_version 2,
source_id collar, wav_topic, model_id, timestamp_us, duration_ms, wav_bytes and truncated.
Use wav_topic to correlate metadata. Truncated indicates the capture limit was reached;
missing metadata is not an assurance that speech was complete. Collar timestamps are
boot-relative and not synchronized with the glove. No training label is attached to
live candidates. FPGA-specific conversion/preprocessing remains with your pipeline.

`receive_clips.py --host YOUR_BROKER_IP` is a ready-to-use subscriber that saves the
received WAV bytes unchanged, checks file structure and avoids duplicate overwrites.
The old numbered PCM audio-packet interface is superseded.
