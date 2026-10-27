# Labelled command recordings for the AI team

Six labels: **sit, come, paw, roll, fetch, bang**. Collect **10 accepted takes per label**, each containing the full phrase **Milo + command**. Total: 60 separate WAV files. This is separate from the ESP's Milo-template training; it does not change the firmware or train a model.

## Start

Keep the working **Collar_Recorder** sketch on the collar FireBeetle. Close Arduino Serial Monitor. Open CMD in this Collar_System folder:

```bat
py -m pip install -r requirements.txt
py collect_commands.py --port COM5
```

Replace COM5 with the collar's actual port. This uses the INMP441 over USB, not a laptop/PC microphone or MQTT. The normal Collar_Mic firmware cannot service these recording requests. The PC playing audio must have working speakers/headphones.

For each take:

1. Wear the mic where it will sit during use. Press Enter when ready.
2. When RECORDING appears, wait about 0.3 seconds and say the displayed phrase ONCE, such as **Milo bang**. Finish within the three-second capture. Do not leave a long, artificial pause between the words.
3. The script plays the recording back. Press Enter to keep it, **r** to retry, **p** to replay, or **q** to stop. Rejected takes are not saved. Speak only during capture, not during playback.
4. Accept only intelligible, correctly spoken examples. The label comes from the prompt; the script does NOT check which words you said. Avoid clipping, coughs, repeated commands, or the end of the command being cut off.

Use natural small variations in pace, tone and loudness rather than copying one file ten times. Avoid deliberately exaggerated voices or moving the mic right to your mouth. Recording integrity checks catch incomplete/zero/corrupted USB captures; they do not judge speech quality.

Run the same command again to resume. It skips existing accepted takes up to the requested count, rather than adding ten more or overwriting them. A partially saved file pair after a crash triggers an error; move that WAV and JSON aside before retrying. If you later find a bad accepted take, move its WAV and matching JSON out of the dataset, then rerun to refill that slot and regenerate the manifest.

To record only one class:

```bat
py collect_commands.py --port COM5 --commands bang
```

## Files to send

```text
command_dataset/
  manifest.csv
  speaker_01/
    sit/sit_01.wav ... sit_10.wav
    come/come_01.wav ... come_10.wav
    paw/paw_01.wav ... paw_10.wav
    roll/roll_01.wav ... roll_10.wav
    fetch/fetch_01.wav ... fetch_10.wav
    bang/bang_01.wav ... bang_10.wav
```

Each WAV also has a matching JSON label file. WAV format: **mono, signed 16-bit PCM, 16,000 Hz, three seconds**. Leading/trailing quiet is retained; no trimming or normalization is applied. Transfer CRC is verified before a take can be accepted.

The generated `manifest.csv` lists relative file path, command label, full prompted transcript (e.g. `Milo bang`), speaker ID, sample rate, duration and UTC capture time. Send the **whole command_dataset folder as a ZIP** so the relative paths and labels stay together. Do not hand-edit the generated CSV; its labels come from the per-take JSON files. You need not send firmware or Wi-Fi credentials.

If a different person records, pass a new ID, for example `--speaker speaker_02`. Keep a person's identity consistent and obtain their permission before recording/sharing. No training/validation/test split is assigned; let the AI teammate choose that split. These 60 single-speaker positives are starter data, not evidence of broad recognition accuracy. Fresh speakers/sessions and noncommand/background examples will be needed to evaluate generalization and false triggers. Do not use these same files as independent accuracy tests after training on them.

The script saves locally (or to your existing OneDrive-synced project folder); it does not upload or send the dataset to your teammate. No actual voice samples are included with the script. Upload Collar_Mic again when you want to resume MQTT operation.
