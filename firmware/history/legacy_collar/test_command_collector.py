"""Offline synthetic checks only; no serial port or playback device is accessed."""
import contextlib
import csv
import io
from pathlib import Path
import unittest
import uuid
import wave
import zlib
import collect_commands as collector


class FakeSerial:
    def __init__(self, pcm, footer=None):
        self.pcm = pcm
        self.position = 0
        self.footer = footer if footer is not None else f'CRC {zlib.crc32(pcm):08x} OK\n'.encode()
    def reset_input_buffer(self): pass
    def write(self, value):
        assert value == b'R'
    def readline(self): return b'MILO_PCM 16000 48000\n'
    def read(self, count):
        out = self.pcm[self.position:self.position + min(count, 701)]
        self.position += len(out)
        return out
    def read_until(self, terminator): return self.footer


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / 'test_output' / ('collector_' + uuid.uuid4().hex)
        self.pcm = b'\x01\x00' * collector.SAMPLES

    def test_serial_capture_crc_and_wav_format(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collector.capture(FakeSerial(self.pcm)), self.pcm)
        with wave.open(io.BytesIO(collector.wav_bytes(self.pcm)), 'rb') as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                             (1, 2, 16000, 48000))

    def test_bad_crc_or_failed_i2s_rejected(self):
        for footer in (b'CRC 00000000 OK\n', b'CRC nonsense OK\n',
                       f'CRC {zlib.crc32(self.pcm):08x} BAD_READ\n'.encode()):
            with self.subTest(footer=footer), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    collector.capture(FakeSerial(self.pcm, footer))

    def test_zero_audio_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            collector.capture(FakeSerial(bytes(collector.PCM_BYTES)))

    def test_all_six_labels_manifest_and_resume(self):
        for command in collector.COMMANDS:
            self.assertFalse(collector.is_saved(self.root, 'speaker_01', command, 1))
            collector.save_take(self.root, 'speaker_01', command, 1, self.pcm)
            self.assertTrue(collector.is_saved(self.root, 'speaker_01', command, 1))
            self.assertFalse(collector.is_saved(self.root, 'speaker_01', command, 2))
        collector.write_manifest(self.root)
        with (self.root / 'manifest.csv').open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({row['label'] for row in rows}, set(collector.COMMANDS))
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertEqual(row['transcript'], 'Milo ' + row['label'])
            self.assertTrue((self.root / row['path']).is_file())

    def test_existing_takes_never_overwritten(self):
        wav = collector.save_take(self.root, 'speaker_01', 'bang', 1, self.pcm)
        original = wav.read_bytes()
        with self.assertRaises(FileExistsError):
            collector.save_take(self.root, 'speaker_01', 'bang', 1, self.pcm)
        self.assertEqual(wav.read_bytes(), original)

    def test_incomplete_pair_detected(self):
        wav, metadata = collector.paths(self.root, 'speaker_01', 'sit', 1)
        wav.parent.mkdir(parents=True)
        wav.write_bytes(collector.wav_bytes(self.pcm))
        with self.assertRaises(RuntimeError):
            collector.is_saved(self.root, 'speaker_01', 'sit', 1)


if __name__ == '__main__': unittest.main()
