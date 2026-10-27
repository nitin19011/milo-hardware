"""Save complete demo pairs; validates the NEW 150x9 + MLW1/WAV contract, never runs mock AI."""
import argparse,csv,getpass,io,json,math,os,re,ssl,struct,time,wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HAND_PROFILE='glove-mpu6050-three-binary-demo-v1'
AUDIO_PROFILE='audio-wav-pcm16-mono-16k-demo-v1'
FEATURES=['ax','ay','az','gx','gy','gz','thumb','index','middle']

def validate_id(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('Invalid capture ID')
    return value

def decode_hand(payload):
    doc=json.loads(payload)
    if doc.get('version')!=1 or doc.get('type')!='hand.clip':raise ValueError('Unknown hand schema')
    d=doc['data'];validate_id(d['capture_id'])
    if not d['valid']:raise ValueError('Glove reported invalid capture: '+str(d.get('faults')))
    if d['profile_id']!=HAND_PROFILE or d['feature_names']!=FEATURES or d['sample_rate_hz']!=50 or d['sample_count']!=150 or d['duration_ms']!=3000:raise ValueError('Wrong glove profile/shape')
    rows=d['samples'];offsets=d['sample_offsets_us']
    if len(rows)!=150 or len(offsets)!=150 or offsets[0]!=0:raise ValueError('Incomplete hand frame')
    if any(type(v) is not int for v in offsets) or any(not 0<b-a<=30000 for a,b in zip(offsets,offsets[1:])):raise ValueError('Bad acquisition offsets')
    if d['last_sample_seq']-d['first_sample_seq']!=149:raise ValueError('Acquisition sequence gap')
    if not 2950000<=offsets[-1]<3000000 or not 0<=doc['timestamp_ms']-d['capture_start_ms']<=30:raise ValueError('Wrong glove time window')
    if d['trigger_source_id']!=doc['source_id'] or d['trigger_boot_id']!=doc['boot_id']:raise ValueError('Wrong trigger identity')
    for row in rows:
        if len(row)!=9 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row):raise ValueError('Non-finite/invalid features')
        if any(v not in (0,1) for v in row[6:]):raise ValueError('Finger features must be BINARY')
    return doc

def decode_audio(payload):
    if len(payload)<8 or payload[:4]!=b'MLW1':raise ValueError('Expected MLW1 + JSON + full WAV (not MLA1/PCM)')
    n=struct.unpack('>I',payload[4:8])[0]
    if n>8192 or len(payload)<8+n+44:raise ValueError('Bad audio header length')
    doc=json.loads(payload[8:8+n]);d=doc['data'];validate_id(d['capture_id']);wav=payload[8+n:]
    if doc.get('version')!=1 or doc.get('type')!='mic.clip' or d['profile_id']!=AUDIO_PROFILE or not d['valid']:raise ValueError('Invalid audio profile')
    if (d['encoding'],d['sample_rate_hz'],d['channels'],d['bits_per_sample'])!=('wav_pcm_s16le',16000,1,16):raise ValueError('Wrong audio metadata')
    if doc['timestamp_ms']!=d['actual_start_ms']:raise ValueError('Wrong audio acquisition timestamp')
    if len(wav)!=96044 or len(wav)!=d['wav_byte_length'] or d['sample_count']!=48000 or d['pcm_byte_length']!=96000:raise ValueError('Wrong WAV length')
    with wave.open(io.BytesIO(wav),'rb') as reader:
        if (reader.getframerate(),reader.getnchannels(),reader.getsampwidth(),reader.getnframes(),reader.getcomptype())!=(16000,1,2,48000,'NONE'):raise ValueError('Wrong WAV format')
        if len(reader.readframes(48000))!=96000:raise ValueError('Truncated PCM')
    if d['actual_end_ms']-d['actual_start_ms']!=3000 or d['duration_ms']!=3000:raise ValueError('Wrong audio duration')
    return doc,wav

class PairSaver:
    def __init__(self,output):self.output=Path(output);self.pending={};self.completed={};self.output.mkdir(parents=True,exist_ok=True)
    def receive(self,kind,payload):
        now=time.monotonic()
        self.pending={k:v for k,v in self.pending.items() if now-v['received']<30}
        self.completed={k:v for k,v in self.completed.items() if now-v<120}
        if kind=='hand':doc=decode_hand(payload);wav=None
        else:doc,wav=decode_audio(payload)
        d=doc['data'];key=validate_id(d['capture_id'])
        if key in self.completed:return None
        item=self.pending.setdefault(key,{'received':now})
        if len(self.pending)>4:
            oldest=min(self.pending,key=lambda k:self.pending[k]['received']);del self.pending[oldest]
            if oldest==key:raise ValueError('Pending pair limit reached')
        if kind in item:
            old=item[kind]
            if old['data']!=doc['data'] or old['source_id']!=doc['source_id'] or old['boot_id']!=doc['boot_id'] or (wav is not None and item['wav']!=wav):raise ValueError('Conflicting duplicate capture')
            return None
        item[kind]=doc
        if wav is not None:item['wav']=wav
        if not {'hand','mic'}.issubset(item):return None
        h=item['hand']['data'];m=item['mic']['data']
        if h['capture_start_ms']!=m['capture_start_ms'] or h['trigger_boot_id']!=m['trigger_boot_id'] or h['trigger_source_id']!=m['trigger_source_id']:raise ValueError('Pair timing/source identity mismatch')
        dest=self.output/key;dest.mkdir(exist_ok=True)
        (dest/'voice.wav').write_bytes(item['wav'])
        for name in ['hand','mic']:(dest/(name+'.json')).write_text(json.dumps(item[name],indent=2),encoding='utf-8')
        with (dest/'glove.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['offset_us',*FEATURES]);w.writerows([t,*v] for t,v in zip(h['sample_offsets_us'],h['samples']))
        self.completed[key]=now;del self.pending[key];return dest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'demo_settings.local.json');p.add_argument('--user');p.add_argument('--output',type=Path,default=ROOT/'received');a=p.parse_args()
    c=json.loads(a.settings.read_text(encoding='utf-8-sig'))
    username=a.user or c.get('monitor_username','monitor')
    password=os.environ.get('MILO_MONITOR_PASSWORD') or (c.get('monitor_password') if username==c.get('monitor_username','monitor') else None) or getpass.getpass('MQTT '+username+' password: ')
    import paho.mqtt.client as mqtt
    saver=PairSaver(a.output);prefix='milo/v1/'+c['session']+'/'
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='demomon'+os.urandom(4).hex(),clean_session=True)
    client.username_pw_set(username,password)
    if c['tls']:
        ca=Path(c['ca_file']);ca=ca if ca.is_absolute() else ROOT/ca
        client.tls_set(ca_certs=str(ca),cert_reqs=ssl.CERT_REQUIRED)
    elif not c.get('allow_local_plaintext_test'):raise ValueError('Plaintext local test not enabled')
    def connected(cl,u,f,reason,props):
        if reason.is_failure:print('Connection rejected:',reason);return
        cl.subscribe([(prefix+'hand/clips',1),(prefix+'mic/clips',1),(prefix+'mic/results',1),(prefix+'status/+',1)])
        print('Monitor connected. Waiting for paired hardware captures; no AI results are simulated.')
    def message(cl,u,msg):
        if msg.retain:return
        try:
            if msg.topic==prefix+'hand/clips':dest=saver.receive('hand',msg.payload)
            elif msg.topic==prefix+'mic/clips':dest=saver.receive('mic',msg.payload)
            else:print(msg.topic,msg.payload.decode('utf-8')[:500]);return
            if dest:print('PAIR SAVED:',dest,'| 150x9 glove + 3s WAV')
        except (ValueError,KeyError,TypeError,wave.Error,EOFError) as e:print('REJECTED:',e)
    client.on_connect=connected;client.on_message=message;client.connect(c['mqtt_host'],c['mqtt_port'],15)
    try:client.loop_forever()
    except KeyboardInterrupt:client.disconnect()

if __name__=='__main__':main()
