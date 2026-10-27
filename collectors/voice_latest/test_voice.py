"""Synthetic-only integrity/resume checks; never connect to hardware or save training data."""
import io,json,math,queue,struct,tempfile,threading,time,unittest,uuid,wave,zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from audio_codec import decode_audio,AUDIO_PROFILE
from voice_core import Dataset,VoiceLink,Clock,COMMANDS,audio_stats,ROOT

def fixture():
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'))
        w.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*.05))) for i in range(48000)))
    wav=out.getvalue();start=int(time.time()*1000)
    doc={'version':1,'type':'mic.clip','source_id':'voice-mic-fast-01','boot_id':uuid.uuid4().hex,'timestamp_ms':start,
      'simulated':True,'data':{'capture_id':uuid.uuid4().hex,'trigger_source_id':'voice-fast-collector','trigger_boot_id':uuid.uuid4().hex,
      'capture_start_ms':start,'duration_ms':3000,'profile_id':AUDIO_PROFILE,'valid':True,'encoding':'wav_pcm_s16le',
      'sample_rate_hz':16000,'channels':1,'bits_per_sample':16,'wav_byte_length':96044,'sample_count':48000,'pcm_byte_length':96000,
      'actual_start_ms':start,'actual_end_ms':start+3000}}
    return doc,wav
def envelope(doc,wav):
    header=json.dumps(doc).encode();return b'MLW1'+struct.pack('>I',len(header))+header+wav

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=ROOT/'.test_output'/uuid.uuid4().hex;self.temp.mkdir(parents=True)
    def test_all_classes_sequential_resume_zip_and_hash(self):
        d=Dataset(self.temp/'session');doc,wav=fixture();stats=audio_stats(wav)
        for label in COMMANDS:
            for n in range(1,11):
                self.assertEqual(d.pending(),(label,n));d.accept(label,n,doc,wav,stats)
        self.assertIsNone(d.pending());self.assertEqual(len(Dataset(d.path).entries),60)
        with zipfile.ZipFile(d.zip_path) as z:
            self.assertEqual(len([n for n in z.namelist() if n.endswith('.wav')]),60)
            self.assertFalse(any('settings' in n or '.h'==Path(n).suffix for n in z.namelist()))
            self.assertEqual(z.read(d.entries[0]['path']),wav)
            self.assertTrue(json.loads(z.read('manifest.json'))['complete'])
        with self.assertRaises(ValueError):d.accept('come',1,doc,wav,stats)
        (d.path/d.entries[0]['path']).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):Dataset(d.path)
    def test_partial_zip_and_rejected_take_not_counted(self):
        d=Dataset(self.temp/'session');doc,wav=fixture()
        self.assertEqual(d.pending(),('come',1))
        # Creating/reviewing a WAV alone never saves it.
        audio_stats(wav);self.assertEqual(len(d.entries),0)
        d.accept('come',1,doc,wav,audio_stats(wav));resumed=Dataset(d.path)
        self.assertEqual(resumed.pending(),('come',2))
        with zipfile.ZipFile(d.zip_path) as z:self.assertFalse(json.loads(z.read('manifest.json'))['complete'])
    def test_decode_rejects_corruption_and_format(self):
        doc,wav=fixture();raw=envelope(doc,wav)
        self.assertEqual(decode_audio(raw)[1],wav)
        for value in [raw[:-1],b'MLA1'+raw[4:],raw[:6]]:
            with self.assertRaises(ValueError):decode_audio(value)
        doc['data']['sample_rate_hz']=8000
        with self.assertRaises(ValueError):decode_audio(envelope(doc,wav))
    def test_callback_filters_old_retained_and_foreign(self):
        link=VoiceLink(lambda *args:None);doc,wav=fixture()
        link.boot=doc['data']['trigger_boot_id'];link.active={'id':doc['data']['capture_id']}
        topic=link.prefix+'mic/clips'
        link.on_message(None,None,SimpleNamespace(topic=topic,retain=True,payload=envelope(doc,wav)))
        self.assertTrue(link.messages.empty())
        doc['data']['capture_id']=uuid.uuid4().hex
        link.on_message(None,None,SimpleNamespace(topic=topic,retain=False,payload=envelope(doc,wav)))
        self.assertTrue(link.messages.empty())
        doc['data']['capture_id']=link.active['id']
        link.on_message(None,None,SimpleNamespace(topic=topic,retain=False,payload=envelope(doc,wav)))
        self.assertEqual(link.messages.get_nowait()[0],'audio')
    def test_capture_flow_and_upload_gate(self):
        link=VoiceLink(lambda *args:None);doc,wav=fixture();calls=[]
        link.clock.offset=time.time()-time.monotonic();link.clock.checked=time.monotonic();link.clock.error=.003
        link.connected.set();link.mic_status=(time.monotonic(),{'state':'online','health':{'capture':'ready','capture_mode':'fast_preroll_v1'}})
        def send(kind,job):
            calls.append((kind,link.clock.now(),job['start']/1000))
            doc['boot_id']='a'*32;doc['data'].update(capture_id=job['id'],capture_start_ms=job['start'])
            if kind=='demo.capture_prepare':link.messages.put(('result',{'type':'demo.capture_ready','boot_id':'a'*32,'data':{'capture_start_ms':job['start'],'capture_mode':'fast_preroll_v1','remaining_record_us':2800000}}))
            if kind=='demo.capture_upload':link.messages.put(('audio',(doc,wav)))
        link.send=send
        result=link.capture();self.assertEqual(result[1],wav)
        self.assertEqual([x[0] for x in calls],['demo.capture_prepare','demo.capture_upload'])
        self.assertLess(calls[-1][1]-calls[0][1],.2) # Upload permission is immediate, not after another timer.
        self.assertIsNone(link.active)
    def test_desktop_uses_same_broker_address_as_mic(self):
        link=VoiceLink(lambda *args:None)
        link.c['mqtt_host']='172.20.10.2';link.c['collector_host']='127.0.0.1'
        # A stale old override must not silently direct the collector to a different listener.
        with patch.object(link.client,'connect') as connect,patch.object(link.client,'loop_start'):
            link.connected.set();link.start();connect.assert_called_once_with('172.20.10.2',1883,15)
    def test_late_confirmation_does_not_reject_intact_audio(self):
        link=VoiceLink(lambda *args:None);doc,wav=fixture()
        link.connected.set();link.mic_status=(time.monotonic(),{'state':'online','health':{'capture':'ready','capture_mode':'fast_preroll_v1'}})
        def send(kind,job):
            doc['boot_id']='b'*32;doc['data'].update(capture_id=job['id'],capture_start_ms=job['start'])
            if kind=='demo.capture_prepare':
                time.sleep(.35)
                link.messages.put(('result',{'type':'demo.capture_ready','boot_id':'b'*32,'_received_monotonic':time.monotonic(),
                  'data':{'capture_start_ms':job['start'],'capture_mode':'fast_preroll_v1','remaining_record_us':2450000}}))
            elif kind=='demo.capture_upload':link.messages.put(('audio',(doc,wav)))
        link.send=send
        result=link.capture()
        self.assertEqual(result[1],wav)
        self.assertGreaterEqual(result[2]['control_confirmation_round_trip_ms'],350)
        self.assertIsNone(link.active)

if __name__=='__main__':unittest.main(verbosity=2)
