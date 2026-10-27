import io,json,re,struct,wave
AUDIO_PROFILE="audio-wav-pcm16-mono-16k-demo-v1"
def validate_id(value):
    if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{32}",value):raise ValueError("Invalid capture ID")
    return value

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
