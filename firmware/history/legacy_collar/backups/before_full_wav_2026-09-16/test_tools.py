"""Offline software checks, NOT speech accuracy or hardware verification."""
import contextlib
import io
import json
from pathlib import Path
import struct
import uuid
import unittest
import wave
import zlib
import numpy as np
import milo
from receive_clips import ClipAssembler

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

    def deliver(self,folder,missing=False,corrupt=False,complete=True):
        receiver=ClipAssembler(folder)
        event={'type':'wake_candidate','source_id':'collar','session_id':17,'clip_id':1,'distance':.05}
        receiver.accept('sensor/collar/voice/event',json.dumps(event))
        audio=(np.arange(640,dtype=np.int16)-320).astype('<i2').tobytes()
        for i in range(2):
            if missing and i==1:continue
            pcm=audio[i*640:(i+1)*640]
            if corrupt and i==1:pcm=bytes([pcm[0]^1])+pcm[1:]
            packet=b'MLA1'+struct.pack('<IIII',17,1,i,320)+pcm
            receiver.accept('sensor/collar/voice/audio',packet)
        event.update(type='voice_candidate',frames=2,complete=complete,
                     crc32=zlib.crc32(audio),truncated=False)
        receiver.accept('sensor/collar/voice/event',json.dumps(event))
        return list(Path(folder).glob('*.wav'))

    def test_complete_audio_reconstructed(self):
        with test_directory() as d,contextlib.redirect_stdout(io.StringIO()):
            files=self.deliver(d);self.assertEqual(len(files),1)
            with wave.open(str(files[0]),'rb') as w:
                self.assertEqual(w.getnframes(),640)
                self.assertEqual(w.getframerate(),16000)

    def test_other_device_packets_ignored(self):
        with test_directory() as d:
            receiver=ClipAssembler(d)
            event={'type':'wake_candidate','source_id':'glove','session_id':17,'clip_id':1,'distance':.05}
            receiver.accept('sensor/glove/voice/event',json.dumps(event))
            receiver.accept('sensor/collar/voice/event',json.dumps(event))
            self.assertEqual(receiver.pending,{})

    def test_missing_corrupt_and_sender_incomplete_rejected(self):
        for options in ({'missing':True},{'corrupt':True},{'complete':False}):
            with test_directory() as d,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.deliver(d,**options),[])

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
        finally:
            milo.ROOT,milo.DATA=oldroot,olddata


if __name__=='__main__':unittest.main()
