"""Clearly simulated wire-format examples, for receiver tests without hardware or AI."""
import io,json,math,struct,uuid,wave

def fixtures():
    key=uuid.uuid4().hex;boot=uuid.uuid4().hex;start=1792134000000
    base={'version':1,'source_id':'hand-01','boot_id':boot,'stream_id':uuid.uuid4().hex,'seq':0,
          'timestamp_ms':start,'capture_us':10000000,'clock_uncertainty_ms':10,'simulated':True}
    job={'capture_id':key,'trigger_source_id':'hand-01','trigger_boot_id':boot,'capture_start_ms':start,'duration_ms':3000}
    hand={**base,'type':'hand.clip','data':{**job,'profile_id':'glove-mpu6050-three-binary-demo-v1',
          'sample_rate_hz':50,'sample_count':150,'feature_names':['ax','ay','az','gx','gy','gz','thumb','index','middle'],
          'samples':[[0,0,9.80665,0,0,0,*([1,1,1] if 50<=i<75 else [0,0,0])] for i in range(150)],
          'sample_offsets_us':[i*20000 for i in range(150)],'first_sample_seq':200,'last_sample_seq':349,'valid':True,'faults':[]}}
    output=io.BytesIO()
    with wave.open(output,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i*2*math.pi*440/16000))) for i in range(48000)))
    wav=output.getvalue()
    header={**base,'source_id':'mic-01','boot_id':uuid.uuid4().hex,'type':'mic.clip','data':{**job,
        'profile_id':'audio-wav-pcm16-mono-16k-demo-v1','encoding':'wav_pcm_s16le','sample_rate_hz':16000,
        'channels':1,'bits_per_sample':16,'sample_count':48000,'wav_byte_length':96044,'pcm_byte_length':96000,
        'actual_start_ms':start,'actual_end_ms':start+3000,'alignment_error_ms':0,'valid':True,'faults':[]}}
    raw=json.dumps(header,separators=(',',':')).encode()
    return hand,b'MLW1'+struct.pack('>I',len(raw))+raw+wav

if __name__=='__main__':
    from pathlib import Path
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('simulated_wire_examples'));a=p.parse_args();a.output.mkdir(exist_ok=True)
    h,b=fixtures();(a.output/'SIMULATED_hand.json').write_text(json.dumps(h,indent=2),encoding='utf-8');(a.output/'SIMULATED_mic_mlw1.bin').write_bytes(b)
    print('SIMULATED fixtures written. These are not real recordings or AI predictions.')
