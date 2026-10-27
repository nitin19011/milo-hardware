"""Collect labelled INMP441 command WAVs using the existing Collar_Recorder firmware.

No MQTT, speech recognition, training, or changes to firmware are performed.
Recordings stay separate from the Milo wake-word enrollment data.
"""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys
import time
import wave
import zlib

COMMANDS = ('sit', 'come', 'paw', 'roll', 'fetch', 'bang')
RATE, SAMPLES, PCM_BYTES = 16000, 48000, 96000
ROOT = Path(__file__).resolve().parent
FIELDS = ('path', 'label', 'transcript', 'speaker_id', 'sample_rate_hz',
          'duration_s', 'recorded_at_utc')


def capture(ser):
    ser.reset_input_buffer()
    ser.write(b'R')
    deadline = time.monotonic() + 5
    while ser.readline().strip() != b'MILO_PCM 16000 48000':
        if time.monotonic() > deadline:
            raise RuntimeError('No recorder header. Upload Collar_Recorder and check the COM port.')
    print('RECORDING: wait a short moment (about 0.3 s), then speak once.')
    pcm = bytearray()
    deadline = time.monotonic() + 6
    while len(pcm) < PCM_BYTES and time.monotonic() < deadline:
        pcm.extend(ser.read(PCM_BYTES - len(pcm)))
    if len(pcm) != PCM_BYTES:
        raise RuntimeError('Incomplete USB recording; nothing saved. Retry.')
    footer = ser.read_until(b'\n').decode('ascii', errors='replace').strip().split()
    try:
        valid = (len(footer) == 3 and footer[0] == 'CRC' and footer[2] == 'OK'
                 and int(footer[1], 16) == zlib.crc32(pcm))
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError('Recording failed the transfer/microphone integrity check; nothing saved.')
    if not any(pcm):
        raise RuntimeError('Audio is entirely zero; check the microphone. Nothing saved.')
    return bytes(pcm)


def wav_bytes(pcm):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as w:
        w.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        w.writeframes(pcm)
    return buffer.getvalue()


def play(wav):
    try:
        import winsound
        print('Playing back through the computer speakers/headphones...')
        winsound.PlaySound(wav, winsound.SND_MEMORY)
        return True
    except (ImportError, RuntimeError) as exc:
        print(f'Automatic playback unavailable: {exc}. Check saved WAVs manually before sharing.')
        return False


def paths(root, speaker, command, number):
    wav = root / speaker / command / f'{command}_{number:02d}.wav'
    return wav, wav.with_suffix('.json')


def is_saved(root, speaker, command, number):
    wav, metadata = paths(root, speaker, command, number)
    if not wav.exists() and not metadata.exists():
        return False
    if not wav.is_file() or not metadata.is_file():
        raise RuntimeError(f'Incomplete existing file pair: {wav}. Move both files aside before retrying; not overwriting.')
    entry = json.loads(metadata.read_text(encoding='utf-8'))
    if (entry.get('label'), entry.get('speaker_id'), entry.get('transcript'), entry.get('path')) != (
            command, speaker, f'Milo {command}', wav.relative_to(root).as_posix()):
        raise RuntimeError(f'Existing metadata does not match its filename: {metadata}')
    with wave.open(str(wav), 'rb') as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) != (1, 2, RATE, SAMPLES):
            raise RuntimeError(f'Existing WAV has unexpected audio format or length: {wav}')
        if len(w.readframes(SAMPLES)) != PCM_BYTES:
            raise RuntimeError(f'Existing WAV is truncated: {wav}')
    return True


def save_take(root, speaker, command, number, pcm):
    if len(pcm) != PCM_BYTES:
        raise ValueError('Expected exactly 3 seconds of signed 16-bit mono PCM.')
    wav, metadata = paths(root, speaker, command, number)
    if wav.exists() or metadata.exists():
        raise FileExistsError(f'Refusing to overwrite an existing take: {wav}')
    wav.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(path=wav.relative_to(root).as_posix(), label=command,
                 transcript=f'Milo {command}', speaker_id=speaker,
                 sample_rate_hz=RATE, duration_s=3,
                 recorded_at_utc=datetime.now(timezone.utc).isoformat())
    # Exclusive creation protects earlier recordings. A crash leaves a detectable
    # incomplete pair, never a silently overwritten sample.
    with wav.open('xb') as f:
        f.write(wav_bytes(pcm))
    with metadata.open('x', encoding='utf-8') as f:
        json.dump(entry, f, indent=2)
    return wav


def write_manifest(root):
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for metadata in sorted(root.glob('*/*/*.json')):
        entry = json.loads(metadata.read_text(encoding='utf-8'))
        expected = metadata.with_suffix('.wav')
        if entry.get('path') != expected.relative_to(root).as_posix() or not expected.is_file():
            raise RuntimeError(f'Metadata/WAV mismatch: {metadata}')
        entries.append(entry)
    # This is a generated index. Per-take JSON remains the source of labels.
    temp = root / 'manifest.csv.tmp'
    with temp.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: entry[key] for key in FIELDS} for entry in entries)
    temp.replace(root / 'manifest.csv')


def run(args):
    import serial
    import numpy as np
    root = Path(args.output).expanduser().resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}', args.speaker):
        raise ValueError('Speaker ID must use letters, digits, underscores or hyphens; e.g. speaker_01.')
    if not 1 <= args.count <= 100:
        raise ValueError('Count must be between 1 and 100 accepted samples per command.')
    pending = [(command, number) for command in args.commands for number in range(1, args.count + 1)
               if not is_saved(root, args.speaker, command, number)]
    write_manifest(root)
    if not pending:
        print('All requested samples already exist. Nothing overwritten.'); return
    print(f'{len(pending)} takes remaining. Output: {root}')
    print('Upload Collar_Recorder, close Serial Monitor, and wear the mic at its collar position.')
    print('Say the WHOLE displayed phrase once. Finish within 3 seconds.')
    print('Playback follows each recording. Enter=keep, r=retry, p=replay, q=quit.')
    print('Labels come from the prompt, NOT automatic speech recognition: listen before accepting!')
    with serial.Serial(args.port, 921600, timeout=.25) as ser:
        time.sleep(2)
        for command, number in pending:
            while True:
                prompt = input(f'\n[{command} {number}/{args.count}] Say "Milo {command}". Enter to record, q to quit: ')
                if prompt.strip().lower() == 'q': return
                try:
                    pcm = capture(ser)
                except RuntimeError as exc:
                    print(exc); continue
                samples = np.frombuffer(pcm, dtype='<i2').astype(np.int32)
                peak = int(np.max(np.abs(samples)))
                clipped = float(np.mean(np.abs(samples) >= 32767))
                print(f'Peak={peak}; full-scale samples={clipped:.1%}')
                if clipped > .01:
                    print('WARNING: likely clipping. Retry with suitable placement/gain before using this take.')
                wav = wav_bytes(pcm)
                play(wav)
                while True:
                    decision = input('Enter=keep, r=retry, p=replay, q=quit: ').strip().lower()
                    if decision == 'p': play(wav); continue
                    if decision in ('', 'r', 'q'): break
                    print('Please use Enter, r, p, or q.')
                if decision == 'q': return
                if decision == 'r': continue
                saved = save_take(root, args.speaker, command, number, pcm)
                write_manifest(root)
                print(f'Saved {saved.relative_to(root)}')
                break
    print(f'Finished. Share the entire folder: {root}')
    print('These are prompted, speaker-labelled examples; no model was trained and no test split was assigned.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='Collar USB serial port, e.g. COM5')
    parser.add_argument('--count', type=int, default=10, help='Target total per command; existing takes are skipped')
    parser.add_argument('--commands', nargs='+', choices=COMMANDS, default=list(COMMANDS))
    parser.add_argument('--speaker', default='speaker_01', help='Anonymous speaker ID; change for each different person')
    parser.add_argument('--output', default=str(ROOT / 'command_dataset'))
    args = parser.parse_args()
    args.commands = list(dict.fromkeys(args.commands))
    try:
        run(args)
    except KeyboardInterrupt:
        print('\nStopped. Accepted takes are saved; rerun the same command to resume.')
    except (OSError, ValueError, RuntimeError, wave.Error) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__': main()
