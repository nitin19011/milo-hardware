import copy,io,json,struct,unittest,wave,uuid
from contextlib import contextmanager
from pathlib import Path
from wire_fixtures import fixtures
from demo_monitor import decode_hand,decode_audio,PairSaver

@contextmanager
def test_folder():
    p=Path(__file__).resolve().parents[1]/'.test_output'/uuid.uuid4().hex
    p.mkdir(parents=True)
    yield str(p)

class Tests(unittest.TestCase):
    def test_full_pair_and_binary(self):
        h,b=fixtures();self.assertEqual(decode_hand(json.dumps(h))['data']['sample_count'],150)
        meta,wav=decode_audio(b);self.assertEqual(len(wav),96044)
        with wave.open(io.BytesIO(wav),'rb') as f:self.assertEqual(f.getnframes(),48000)
        for first in ['hand','mic']:
            with test_folder() as tmp:
                saver=PairSaver(tmp)
                blobs={'hand':json.dumps(h).encode(),'mic':b}
                self.assertIsNone(saver.receive(first,blobs[first]));second='mic' if first=='hand' else 'hand'
                dest=saver.receive(second,blobs[second]);self.assertTrue((dest/'voice.wav').is_file())
                self.assertEqual(len((dest/'glove.csv').read_text(encoding='utf-8').splitlines()),151)
                self.assertIsNone(saver.receive(first,blobs[first]))
    def test_corruption_and_old_profiles_rejected(self):
        h,b=fixtures()
        for mutate in [lambda x:x['data']['samples'][0].__setitem__(6,1369),lambda x:x['data'].__setitem__('sample_count',100),
                       lambda x:x['data'].__setitem__('valid',False),lambda x:x['data'].__setitem__('profile_id','glove-mpu6050-thumb-index-v4-raw'),
                       lambda x:x['data']['sample_offsets_us'].__setitem__(5,999999)]:
            v=copy.deepcopy(h);mutate(v)
            with self.assertRaises(ValueError):decode_hand(json.dumps(v))
        for bad in [b[:-1],b+bytes(1),b'MLA1'+b[4:],b'MLW1'+struct.pack('>I',99999)+b[8:]]:
            with self.assertRaises(ValueError):decode_audio(bad)
    def test_pairs_never_mix(self):
        h,b=fixtures();other,b2=fixtures()
        with test_folder() as tmp:
            s=PairSaver(tmp);self.assertIsNone(s.receive('hand',json.dumps(h)));self.assertIsNone(s.receive('mic',b2));self.assertEqual(list(Path(tmp).iterdir()),[])
            self.assertIsNotNone(s.receive('mic',b))
    def test_timing_identity_mismatch(self):
        h,b=fixtures();n=struct.unpack('>I',b[4:8])[0];d=json.loads(b[8:8+n]);d['data']['trigger_boot_id']='f'*32
        header=json.dumps(d).encode();bad=b'MLW1'+struct.pack('>I',len(header))+header+b[8+n:]
        with test_folder() as tmp:
            s=PairSaver(tmp);s.receive('hand',json.dumps(h))
            with self.assertRaises(ValueError):s.receive('mic',bad)
    def test_shared_headers_and_no_insecure_tls(self):
        root=Path(__file__).resolve().parents[1]
        for header in (root/'shared').glob('*.h'):
            for name in ['GloveDemo','MicDemo']:self.assertEqual(header.read_bytes(),(root/name/header.name).read_bytes())
        all_source=''.join(p.read_text(encoding='utf-8') for p in (root/'shared').glob('*.h'))
        self.assertNotIn('setInsecure',all_source)
        for name in ['GloveDemo','MicDemo']:
            self.assertEqual(len(list((root/name).glob('*.ino'))),1)

if __name__=='__main__':unittest.main(verbosity=2)
