"""Validate Milo demo MQTT inputs; copied from the production receiver, 18 Oct 2026.
Mic input must be original binary msg.payload, not a text export.
"""
import io,json,math,re,struct,wave
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
