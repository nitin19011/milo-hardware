"""Offline software checks, NOT speech accuracy or hardware verification."""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import struct
import uuid
import unittest
import wave
import zlib
import numpy as np
import milo
from receive_clips import WavReceiver, validate_wav

@contextlib.contextmanager
def test_directory():
    # Keep generated test artifacts separate from real recordings and model headers.
    path=Path(__file__).parent/'test_output'/uuid.uuid4().hex
    path.mkdir(parents=True)
    yield str(path)

class ToolsTests(unittest.TestCase):
    def test_features_finite_and_dc_invariant(self):
        rng=np.random.default_rng(24)
        x=rng.integers(-3000,3000,3200,dtype=np.int16)
        a,r=milo.features(x);b,s=milo.features(x+100)
        self.assertEqual(a.shape,(10,12))
        self.assertTrue(np.isfinite(a).all())
        np.testing.assert_allclose(a,b,atol=1e-5)
        np.testing.assert_allclose(r,s,atol=1e-3)

    def test_known_sequence_detected_and_silence_rejected(self):
        rng=np.random.default_rng(3)
        x=rng.normal(size=(20,12)).astype(np.float32)
        x/=np.linalg.norm(x,axis=1,keepdims=True)
        template=np.rint(x*127).astype(np.int8).astype(np.float32)/127
        score,end=milo.scan(x,np.full(20,100.),[template],8.)
        self.assertLess(score,.001);self.assertEqual(end,19)
        score,_=milo.scan(x,np.zeros(20),[template],8.)
        self.assertGreater(score,1e8)

    def wav(self,frames=200):
        pcm=(np.arange(frames*320,dtype=np.int32)%1000).astype('<i2').tobytes()
        stream=io.BytesIO()
        with wave.open(stream,'wb') as w:
            w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(pcm)
        return stream.getvalue()

    def test_whole_wav_over_64k_saved_unchanged(self):
        payload=self.wav()
        self.assertEqual(len(payload),128044)
        self.assertEqual(validate_wav(payload),4)
        with test_directory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=WavReceiver(d);p=r.accept('sensor/collar/voice/wav/1234abcd/1',payload)
            self.assertEqual(p.read_bytes(),payload)
            self.assertIsNone(r.accept('sensor/collar/voice/wav/1234abcd/1',payload))
            self.assertEqual(len(list(Path(d).glob('*.wav'))),1)

    def test_incomplete_wrong_format_and_oversize_rejected(self):
        valid=self.wav()
        damaged=bytearray(valid);damaged[24:28]=struct.pack('<I',8000)
        for payload in (b'',valid[:-2],valid+b'00',bytes(damaged),b'MLA1'+bytes(656)):
            with self.subTest(length=len(payload)),self.assertRaises(ValueError):
                validate_wav(payload)

    def test_old_topics_and_other_devices_ignored(self):
        with test_directory() as d:
            r=WavReceiver(d)
            for topic in ('sensor/glove/voice/wav/1234abcd/1','sensor/collar/voice/audio',
                          'sensor/collar/voice/wav/../../file'):
                self.assertIsNone(r.accept(topic,self.wav()))
            self.assertEqual(list(Path(d).glob('*')),[])

    def test_metadata_optional_and_id_collision_protected(self):
        with test_directory() as d,contextlib.redirect_stdout(io.StringIO()):
            r=WavReceiver(d);topic='sensor/collar/voice/wav/1234abcd/1'
            p=r.accept(topic,self.wav())
            self.assertTrue(p.exists()) # WAV requires no metadata event.
            event={'schema_version':2,'source_id':'collar','wav_topic':topic,
                   'wav_bytes':128044,'truncated':True}
            r.accept('sensor/collar/voice/event',json.dumps(event).encode())
            self.assertTrue(p.with_suffix('.json').exists())
            with self.assertRaises(ValueError):r.accept(topic,self.wav(100))

    def test_synthetic_training_export_and_evaluation(self):
        # Synthesized tones exercise the pipeline only; they are NOT a Milo model.
        oldroot,olddata=milo.ROOT,milo.DATA
        try:
            with test_directory() as d,contextlib.redirect_stdout(io.StringIO()):
                milo.ROOT=Path(d);milo.DATA=Path(d)/'recordings'
                (Path(d)/'Collar_Mic').mkdir()
                rng=np.random.default_rng(17)
                for group in milo.GROUPS:
                    folder=milo.DATA/group;folder.mkdir(parents=True)
                    for j in range(8):
                        x=np.zeros(48000,dtype=np.int16)
                        for f in range(12):
                            t=np.arange(320)/16000
                            freq=400+f*95 if 'negative' not in group else 3500+f*80
                            tone=2500*np.sin(2*np.pi*freq*t)+rng.normal(0,1,320)
                            x[(20+f)*320:(21+f)*320]=tone.astype(np.int16)
                        with wave.open(str(folder/f'{j}.wav'),'wb') as w:
                            w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(x.astype('<i2').tobytes())
                milo.train(None);milo.evaluate(None)
                header=(Path(d)/'Collar_Mic'/'milo_model.h').read_text()
                self.assertIn('MILO_COUNT = 8',header)
                self.assertEqual(json.loads((Path(d)/'test_report.json').read_text())['misses'],0)
                # Tuned clips stay on disk but cannot inflate fresh test results.
                model_path=Path(d)/'model.json'
                model=json.loads(model_path.read_text())
                model['tuning_recording_hashes']=[hashlib.sha256((milo.DATA/g/'0.wav').read_bytes()).hexdigest()
                    for g in ('test_positive','test_negative')]
                model_path.write_text(json.dumps(model))
                milo.evaluate(None)
                report=json.loads((Path(d)/'test_report.json').read_text())
                self.assertEqual(len(report['positive']),7)
                self.assertEqual(len(report['negative']),7)
                self.assertEqual(report['tuning_recordings_excluded'],2)
                model['tuning_recording_hashes']=[hashlib.sha256(p.read_bytes()).hexdigest()
                    for g in ('test_positive','test_negative') for p in (milo.DATA/g).glob('*.wav')]
                model_path.write_text(json.dumps(model))
                with self.assertRaisesRegex(ValueError,'fresh'):
                    milo.evaluate(None)
        finally:
            milo.ROOT,milo.DATA=oldroot,olddata


if __name__=='__main__':unittest.main()
