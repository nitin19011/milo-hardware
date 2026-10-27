"""Record, enroll, calibrate and evaluate a speaker-specific Milo DTW detector.

All recordings come from the INMP441, not the laptop microphone.
No neural network is trained. Templates are MFCC-like acoustic references.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import time
import wave
import zlib
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "recordings"
RATE, FRAME, FFT, MEL, COEFF = 16000, 320, 512, 20, 12
GROUPS = ("templates", "cal_positive", "cal_negative", "test_positive", "test_negative")


def tables():
    window = np.hanning(FRAME).astype(np.float32)
    edges = 700 * (10 ** (np.linspace(2595*np.log10(1+100/700),
                                    2595*np.log10(1+7600/700), MEL+2)/2595)-1)
    hz = np.arange(FFT//2+1)*RATE/FFT
    weights = np.array([np.maximum(0, np.minimum((hz-a)/(b-a), (c-hz)/(c-b)))
                        for a,b,c in zip(edges[:-2],edges[1:-1],edges[2:])], dtype=np.float32)
    dct = np.cos(np.pi*np.arange(1,COEFF+1)[:,None]*(np.arange(MEL)+.5)/MEL).astype(np.float32)
    return window, weights, dct

WINDOW, WEIGHTS, DCT = tables()


def features(pcm):
    count = len(pcm)//FRAME
    if not count:
        return np.empty((0,COEFF),dtype=np.float32), np.empty(0)
    blocks = np.asarray(pcm[:count*FRAME], dtype=np.float32).reshape(count,FRAME)
    levels = np.sqrt(np.mean((blocks-blocks.mean(axis=1,keepdims=True))**2,axis=1))
    blocks = (blocks-blocks.mean(axis=1,keepdims=True))/32768
    spectrum = np.fft.rfft(blocks*WINDOW, FFT)
    power = (spectrum.real**2+spectrum.imag**2)/FFT
    logmel = np.log(np.maximum(power @ WEIGHTS.T, 1e-12))
    feat = logmel @ DCT.T
    feat /= np.maximum(np.linalg.norm(feat,axis=1,keepdims=True), 1e-9)
    return feat.astype(np.float32), levels


def load_wav(path):
    with wave.open(str(path),'rb') as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate()) != (1,2,RATE):
            raise ValueError(f'{path.name}: expected mono 16-bit 16 kHz WAV')
        pcm = np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').copy()
    if len(pcm) < RATE//2:
        raise ValueError(f'{path.name}: recording too short')
    return pcm


def scan(feat, levels, templates, floor):
    """Same streaming subsequence-DTW recurrence and tie ordering as firmware."""
    prev = [np.r_[0., np.full(len(t),1e9)].astype(np.float32) for t in templates]
    starts = [np.zeros(len(t)+1,dtype=np.int32) for t in templates]
    best, end = 1e9, -1
    for f, x in enumerate(feat):
        if levels[f] < floor:
            for p in prev: p[1:] = 1e9
            continue
        for k, t in enumerate(templates):
            p, st = prev[k], starts[k]
            q = np.full(len(t)+1,1e9,dtype=np.float32); q[0]=0
            ns = np.zeros(len(t)+1,dtype=np.int32); ns[0]=f
            distances = np.sum((t-x)**2,axis=1)
            for j in range(1,len(t)+1):
                cost = float(p[j-1]); start = f if j==1 else int(st[j-1])
                if p[j] < cost: cost=float(p[j]); start=int(st[j])
                if q[j-1] < cost: cost=float(q[j-1]); start=int(ns[j-1])
                q[j]=cost+distances[j-1]; ns[j]=start
            elapsed=f-int(ns[-1])+1
            score=float(q[-1])/(len(t)+elapsed)
            if max(1,len(t)//2) <= elapsed <= len(t)*2 and score < best:
                best,end=score,f
            prev[k], starts[k]=q,ns
    return best,end


def collect(args):
    import serial
    folder=DATA/args.group
    folder.mkdir(parents=True,exist_ok=True)
    guidance = {
      'templates':'Say ONLY Milo once. Vary normal speed and glove position.',
      'cal_positive':'Say Milo sit / Milo come / Milo fetch naturally, without a pause.',
      'cal_negative':'Speech WITHOUT Milo, similar words (my low, hello, pillow), or glove noise.',
      'test_positive':'FRESH Milo + command recordings; vary position and volume.',
      'test_negative':'FRESH speech WITHOUT Milo and realistic background/movement noise.'}
    print(guidance[args.group])
    print('For EVERY recording: stay quiet for the first 0.3 seconds, then speak.')
    print('Close Arduino Serial Monitor. Upload Collar_Recorder first.')
    with serial.Serial(args.port,921600,timeout=.25) as ser:
        time.sleep(2)
        for i in range(args.count):
            input(f'[{i+1}/{args.count}] Press Enter when ready...')
            ser.reset_input_buffer(); ser.write(b'R')
            deadline=time.monotonic()+5
            while True:
                header=ser.readline()
                if header.strip()==b'MILO_PCM 16000 48000': break
                if time.monotonic()>deadline:
                    raise RuntimeError('No recording header. Check port and recorder firmware.')
            print('Recording 3 seconds. Speak after a short quiet moment.')
            payload=bytearray(); deadline=time.monotonic()+6
            while len(payload)<96000 and time.monotonic()<deadline:
                payload.extend(ser.read(96000-len(payload)))
            if len(payload)!=96000: raise RuntimeError('Incomplete recording; nothing saved.')
            footer=ser.read_until(b'\n').decode('ascii',errors='replace').strip().split()
            if len(footer)!=3 or footer[0]!='CRC' or footer[2]!='OK' or int(footer[1],16)!=zlib.crc32(payload):
                raise RuntimeError('Recording failed integrity check; nothing saved. Try again.')
            pcm=np.frombuffer(payload,dtype='<i2')
            if not np.any(pcm): raise RuntimeError('All-zero audio. Check microphone.')
            clipped=float(np.mean(np.abs(pcm.astype(np.int32))>=32767))
            name=folder/f'{time.time_ns()}.wav'
            with wave.open(str(name),'wb') as w:
                w.setparams((1,2,RATE,0,'NONE','not compressed')); w.writeframes(payload)
            print(f'Saved {name.name}; peak={np.max(np.abs(pcm.astype(np.int32)))}; clipped={clipped:.1%}')
            if clipped>.01: print('WARNING: clipping. Reduce gain consistently in BOTH sketches and re-record.')


def array_cpp(name, arr, ctype='float'):
    arr=np.asarray(arr)
    shape=''.join(f'[{n}]' for n in arr.shape)
    def fmt(a):
        if a.ndim==1:
            return '{'+','.join((f'{float(v):.9e}f' if ctype=='float' else str(int(v))) for v in a)+'}'
        return '{\n'+',\n'.join(fmt(row) for row in a)+'\n}'
    return f'static const {ctype} {name}{shape} = {fmt(arr)};\n'


def scores_for(group, templates, floor, excluded_hashes=()):
    scores=[]
    for p in sorted((DATA/group).glob('*.wav')):
        if excluded_hashes and hashlib.sha256(p.read_bytes()).hexdigest() in excluded_hashes:
            continue
        feat,levels=features(load_wav(p))
        score,end=scan(feat,levels,templates,floor)
        scores.append({'file':str(p.relative_to(ROOT)), 'score':score,'end_ms':(end+1)*20})
    return scores


def train(args):
    paths=sorted((DATA/'templates').glob('*.wav'))
    if not 6 <= len(paths) <= 12:
        raise ValueError('Use 6–12 template WAVs; recommended 8. Move unwanted WAVs out of templates.')
    signals=[load_wav(p) for p in paths]
    # First 0.3 seconds must be quiet. This is a simple energy gate, NOT a speech classifier.
    noise=np.concatenate([features(s)[1][:15] for s in signals])
    floor=max(8.,float(np.median(noise))*2.0)
    templates=[]
    for p,pcm in zip(paths,signals):
        feat,levels=features(pcm)
        threshold=max(floor,float(np.max(levels))*.08)
        active=np.flatnonzero(levels>=threshold)
        if not len(active): raise ValueError(f'{p.name}: no usable speech')
        a,b=int(active[0]),int(active[-1])+1
        if a<10: raise ValueError(f'{p.name}: first 0.3 seconds must be quiet; re-record')
        if not 8 <= b-a <= 60:
            raise ValueError(f'{p.name}: expected Milo alone lasting 0.16–1.2 s; re-record')
        # Exclude boundary silence; preserve full consonant/vowel sequence inside.
        templates.append(np.clip(np.rint(feat[a:b]*127),-127,127).astype(np.int8))
    decoded=[t.astype(np.float32)/127 for t in templates]
    positive=scores_for('cal_positive',decoded,floor)
    negative=scores_for('cal_negative',decoded,floor)
    if len(positive)<8 or len(negative)<8:
        raise ValueError('Collect at least 8 cal_positive and 8 cal_negative recordings first.')
    if any(p['score']>=1e8 for p in positive):
        raise ValueError('A positive clip never matched a valid-duration voiced segment. Check audio/noise gate.')
    cutoff=max(p['score'] for p in positive)*1.05+1e-5
    if cutoff > .20:
        print('WARNING: positive matches are weak. Re-record templates; do not rely on this detector yet.')
    model={'version':1,'threshold':cutoff,'energy_floor':floor,
           'templates':[t.tolist() for t in templates],
           'template_files':[str(p.relative_to(ROOT)) for p in paths]}
    model['id']=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()[:12]
    (ROOT/'model.json').write_text(json.dumps(model,indent=2))
    export(model)
    report={'model_id':model['id'],'threshold':cutoff,'energy_floor':floor,
            'calibration_positive':positive,'calibration_negative':negative,
            'calibration_misses':sum(p['score']>cutoff for p in positive),
            'calibration_false_trigger_clips':sum(p['score']<=cutoff for p in negative)}
    (ROOT/'calibration_report.json').write_text(json.dumps(report,indent=2))
    print(f'Model {model["id"]} exported into Collar_Mic/Collar_Mic.ino')
    print(f'Calibration: misses {report["calibration_misses"]}/{len(positive)}, '
          f'false-trigger clips {report["calibration_false_trigger_clips"]}/{len(negative)}.')
    print('These are tuning results, NOT independent accuracy. Now collect test groups and run evaluate.')


def export(model):
    ts=[np.array(t,dtype=np.int8) for t in model['templates']]
    lines=[
           f'static constexpr int MILO_COUNT = {len(ts)};\n',
           f'static constexpr int MILO_MAX_FRAMES = {max(map(len,ts))};\n',
           f'static constexpr float MILO_THRESHOLD = {model["threshold"]:.9e}f;\n',
           f'static constexpr float MILO_ENERGY_FLOOR = {model["energy_floor"]:.9e}f;\n',
           f'static const char MILO_MODEL_ID[] = "{model["id"]}";\n',
           array_cpp('MILO_WINDOW',WINDOW),array_cpp('MILO_MEL',WEIGHTS),array_cpp('MILO_DCT',DCT)]
    for i,t in enumerate(ts): lines.append(array_cpp(f'MILO_T{i}',t,'int8_t'))
    lines.append('static const int8_t * const MILO_TEMPLATES[] = {'+
                 ','.join(f'&MILO_T{i}[0][0]' for i in range(len(ts)))+'};\n')
    lines.append(array_cpp('MILO_LENGTHS',np.array(list(map(len,ts))),'int'))
    sketch=ROOT/'Collar_Mic'/'Collar_Mic.ino'
    text=sketch.read_text()
    begin='// BEGIN MILO MODEL\n'
    end='// END MILO MODEL'
    if text.count(begin)!=1 or text.count(end)!=1:
        raise ValueError('Sketch must contain exactly one pair of MILO MODEL markers; nothing changed.')
    start=text.index(begin)+len(begin)
    stop=text.index(end)
    if stop<start:
        raise ValueError('MILO MODEL markers are reversed; nothing changed.')
    sketch.write_text(text[:start]+''.join(lines)+text[stop:])


def evaluate(args):
    model=json.loads((ROOT/'model.json').read_text())
    ts=[np.array(t,dtype=np.float32)/127 for t in model['templates']]
    # Once a test clip informs threshold tuning, it is no longer independent.
    used_for_tuning=set(model.get('tuning_recording_hashes', []))
    pos=scores_for('test_positive',ts,model['energy_floor'],used_for_tuning)
    neg=scores_for('test_negative',ts,model['energy_floor'],used_for_tuning)
    if not pos or not neg:
        raise ValueError('Record fresh test_positive and test_negative clips. Recordings already used for tuning are excluded.')
    # Reject exact duplicates across development and test groups.
    dev={hashlib.sha256(p.read_bytes()).hexdigest() for g in GROUPS[:3] for p in (DATA/g).glob('*.wav')}
    for g in GROUPS[3:]:
        for p in (DATA/g).glob('*.wav'):
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            if digest in used_for_tuning:
                continue
            if digest in dev:
                raise ValueError(f'{p.name}: test recording duplicates development data')
    cutoff=model['threshold']
    report={'model_id':model['id'],'threshold':cutoff,'positive':pos,'negative':neg,
            'tuning_recordings_excluded':sum(hashlib.sha256(p.read_bytes()).hexdigest() in used_for_tuning
                for g in GROUPS[3:] for p in (DATA/g).glob('*.wav')),
            'misses':sum(p['score']>cutoff for p in pos),
            'false_trigger_clips':sum(p['score']<=cutoff for p in neg)}
    (ROOT/'test_report.json').write_text(json.dumps(report,indent=2))
    print(f'Independent test: missed {report["misses"]}/{len(pos)} command clips; '
          f'false-triggered on {report["false_trigger_clips"]}/{len(neg)} negative clips.')
    print('This measures wake detection only, not clip completeness or MQTT delivery.')
    print('Conversation that actually contains Milo is a wake-positive, even when it is not a command.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    r=sub.add_parser('record'); r.add_argument('--port',required=True)
    r.add_argument('--group',choices=GROUPS,required=True); r.add_argument('--count',type=int,default=8)
    r.set_defaults(func=collect)
    sub.add_parser('train').set_defaults(func=train)
    sub.add_parser('evaluate').set_defaults(func=evaluate)
    args=parser.parse_args()
    try: args.func(args)
    except (ValueError,RuntimeError,FileNotFoundError) as exc: parser.exit(1,f'Error: {exc}\n')

if __name__=='__main__': main()
