"""Wireless mic control and lossless, resumable labelled WAV datasets."""
import array,csv,hashlib,io,json,math,os,queue,socket,ssl,struct,threading,time,uuid,wave,zipfile
from datetime import datetime,timezone
from pathlib import Path
from audio_codec import decode_audio,AUDIO_PROFILE

ROOT=Path(__file__).resolve().parent
COMMANDS=('come','sit','paw','spin','bang','fetch')
COUNT=10

class Clock:
    """Desktop display timer only. The mic schedules its own relative recording window."""
    def __init__(self):self.offset=time.time()-time.monotonic();self.checked=time.monotonic();self.error=0
    def now(self):return time.monotonic()+self.offset
    def sync(self,hosts):pass
    def fresh(self,hosts):return 0


def audio_stats(wav):
    with wave.open(io.BytesIO(wav),'rb') as w:pcm=w.readframes(w.getnframes())
    samples=array.array('h');samples.frombytes(pcm)
    if __import__('sys').byteorder!='little':samples.byteswap()
    peak=max(abs(v) for v in samples);rms=math.sqrt(sum(v*v for v in samples)/len(samples))
    clipped=sum(v>=32767 or v<=-32768 for v in samples)/len(samples)
    warnings=[]
    if rms<30:warnings.append('Very quiet: listen carefully and retry if speech is unclear.')
    if clipped>.01:warnings.append('More than 1% clipped samples: retry with better placement/lower speaking volume.')
    return {'peak':peak,'rms':round(rms,2),'rms_dbfs':round(20*math.log10(max(rms,1e-9)/32768),2),'clipped_fraction':clipped,'warnings':warnings}

class VoiceLink:
    def __init__(self,notify):
        import paho.mqtt.client as mqtt
        self.c=json.loads((ROOT/'voice_settings.local.json').read_text(encoding='utf-8-sig'))
        self.notify=notify;self.clock=Clock();self.boot=uuid.uuid4().hex;self.seq=0
        self.prefix='milo/v1/'+self.c['session']+'/'
        self.connected=threading.Event();self.messages=queue.Queue(maxsize=24)
        self.lock=threading.Lock();self.active=None;self.mic_status=None;self.sub_error=None
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='voicetr'+uuid.uuid4().hex[:14],clean_session=True)
        if self.c.get('collector_username'):self.client.username_pw_set(self.c['collector_username'],self.c['collector_password'])
        if self.c['tls']:self.client.tls_set(ca_certs=str(ROOT/self.c['ca_file']),cert_reqs=ssl.CERT_REQUIRED)
        elif not self.c.get('allow_local_plaintext_test'):raise ValueError('Local broker mode must be explicit.')
        self.client.max_inflight_messages_set(4);self.client.max_queued_messages_set(8)
        self.client.on_connect=self.on_connect;self.client.on_subscribe=self.on_subscribe
        self.client.on_disconnect=self.on_disconnect;self.client.on_message=self.on_message
    def start(self):
        self.clock.sync(self.c['ntp_servers'])
        self.client.connect(self.c['mqtt_host'],self.c['mqtt_port'],15);self.client.loop_start()
        if not self.connected.wait(12):raise RuntimeError(self.sub_error or 'Broker connection/subscription timed out.')
        self.notify('connected',f"Connected to {self.c['mqtt_host']}:{self.c['mqtt_port']}. Mic only; glove stays off.")
    def on_connect(self,cl,u,flags,reason,props):
        if reason.is_failure:self.sub_error='MQTT login rejected: '+str(reason);return
        cl.subscribe([(self.prefix+s,1) for s in ['mic/results','mic/clips','status/+']])
    def on_subscribe(self,cl,u,mid,reasons,props):
        if len(reasons)!=3 or any(r.is_failure for r in reasons):self.sub_error='Collector subscription denied.';return
        self.connected.set()
    def on_disconnect(self,cl,u,flags,reason,props):
        self.connected.clear();self.notify('connection','Disconnected; waiting for reconnection.')
        with self.lock:active=self.active
        if active:
            try:self.messages.put_nowait(('error','Network disconnected during capture. Retry.'))
            except queue.Full:pass
    def on_message(self,cl,u,msg):
        try:
            if msg.topic.startswith(self.prefix+'status/'):
                doc=json.loads(msg.payload)
                if doc.get('source_id')==self.c['mic_source_id']:
                    self.mic_status=(time.monotonic(),doc)
                    health=doc.get('health',{});self.notify('mic','Mic '+str(health.get('capture',doc.get('state','offline'))))
                return
            if msg.retain:return
            with self.lock:active=self.active
            if not active:return
            if msg.topic==self.prefix+'mic/clips':doc,wav=decode_audio(msg.payload);item=('audio',(doc,wav))
            else:
                doc=json.loads(msg.payload);doc['_received_monotonic']=time.monotonic();item=('result',doc)
            d=doc.get('data',{})
            if doc.get('source_id')!=self.c['mic_source_id'] or d.get('capture_id')!=active['id'] or d.get('trigger_boot_id')!=self.boot or d.get('trigger_source_id')!=self.c['hand_source_id']:return
            self.messages.put_nowait(item)
        except (ValueError,KeyError,TypeError,wave.Error,queue.Full):
            # A malformed packet never becomes a labelled training example.
            return
    def send(self,kind,job):
        self.seq+=1
        data={'capture_id':job['id'],'target_source_id':self.c['mic_source_id'],
          'capture_start_ms':job['start'],'duration_ms':3000,'expires_at_ms':job['start']+18000,
          'upload_not_before_ms':job['start']+3000,'requested_profile_id':AUDIO_PROFILE,'start_delay_ms':0,'capture_mode':'fast_preroll_v1'}
        doc={'version':1,'type':kind,'source_id':self.c['hand_source_id'],'boot_id':self.boot,
          'stream_id':self.boot,'seq':self.seq,'timestamp_ms':int(self.clock.now()*1000),
          'capture_us':int(time.monotonic()*1e6),'clock_uncertainty_ms':self.clock.fresh(self.c['ntp_servers']),'data':data}
        info=self.client.publish(self.prefix+'mic/capture',json.dumps(doc,separators=(',',':')),qos=1,retain=False)
        info.wait_for_publish(timeout=2)
        if not info.is_published():raise RuntimeError('Capture control was not acknowledged by broker.')
    def capture(self):
        if not self.connected.is_set():raise RuntimeError('Collector is not connected. Wait for reconnection.')
        status=self.mic_status
        if not status or time.monotonic()-status[0]>12 or status[1].get('health',{}).get('capture')!='ready' or status[1].get('state')!='online':raise RuntimeError('Mic is not Ready. Check it is running MicVoiceFast, connected to the same hotspot as the laptop. Wait a few seconds and retry.')
        if status[1].get('health',{}).get('capture_mode')!='fast_preroll_v1':raise RuntimeError('Flash the new MicVoiceFast sketch for this collector.')
        self.clock.fresh(self.c['ntp_servers'])
        pressed=time.monotonic()
        job={'id':uuid.uuid4().hex,'start':int(self.clock.now()*1000)}
        with self.lock:self.active=job
        while not self.messages.empty():self.messages.get_nowait()
        success=False
        try:
            self.send('demo.capture_prepare',job);ready=None
            while time.monotonic()<pressed+2:
                try:kind,value=self.messages.get(timeout=.1)
                except queue.Empty:continue
                if kind=='error':raise RuntimeError(value)
                if kind=='result':
                    if value['type']=='demo.capture_failed':raise RuntimeError('Mic rejected capture: '+value['data'].get('reason','unknown'))
                    if value['type']=='demo.capture_ready':
                        remaining=value['data'].get('remaining_record_us')
                        if value['data'].get('capture_mode')!='fast_preroll_v1' or not isinstance(remaining,int) or not 0<remaining<=3000000:raise RuntimeError('Mic did not confirm fast recording mode; check the flashed sketch.')
                        ready=value;break
            if ready is None:raise RuntimeError('Mic did not confirm readiness in time. Nothing saved; retry.')
            job['start']=ready['data']['capture_start_ms']
            end_mono=ready.get('_received_monotonic',time.monotonic())+ready['data']['remaining_record_us']/1e6
            self.notify('scheduled',(end_mono-3,end_mono))
            # Grant upload now; the ESP only publishes once all 48,000 samples are frozen.
            self.send('demo.capture_upload',job)
            while time.monotonic()<pressed+16:
                try:kind,value=self.messages.get(timeout=.05)
                except queue.Empty:continue
                if kind=='error':raise RuntimeError(value)
                if kind=='result' and value['type']=='demo.capture_failed':raise RuntimeError('Mic capture failed: '+value['data'].get('reason','unknown'))
                if kind=='audio':
                    doc,wav=value;d=doc['data']
                    if d['capture_start_ms']!=job['start'] or doc['boot_id']!=ready['boot_id']:raise RuntimeError('Mic identity/timing changed during capture.')
                    stats=audio_stats(wav)
                    # This includes outbound control, ESP handling and the return acknowledgement.
                    # A late confirmation does not establish when recording began or prove lost speech.
                    stats['control_confirmation_round_trip_ms']=round(1000*(ready.get('_received_monotonic',time.monotonic())-pressed),2)
                    if stats['peak']==0:raise RuntimeError('Microphone returned all-zero audio. Check wiring; nothing saved.')
                    success=True;return doc,wav,stats
            raise RuntimeError('WAV upload timed out. Nothing saved; retry.')
        finally:
            if not success and self.connected.is_set():
                try:self.send('demo.capture_cancel',job)
                except Exception:pass
            with self.lock:self.active=None
    def close(self):self.client.disconnect();self.client.loop_stop()

class Dataset:
    def __init__(self,path=None):
        self.path=Path(path) if path else ROOT/'datasets'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
        self.path.mkdir(parents=True,exist_ok=True)
        p=self.path/'session.json'
        config={'schema':'milo-voice-training-v1','speaker_id':'Nitin','commands':list(COMMANDS),'accepted_per_command':COUNT,
          'transcript_template':'Milo {label}','sample_rate_hz':16000,'channels':1,'sample_width_bytes':2,'duration_s':3,
          'created_at_utc':datetime.now(timezone.utc).isoformat(),'labels':'prompt label confirmed by user; no automatic playback or speech recognition'}
        if p.exists():
            c=json.loads(p.read_text(encoding='utf-8'))
            if c.get('schema')!=config['schema'] or c.get('commands')!=config['commands']:raise ValueError('Not a compatible voice dataset.')
        else:p.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        (self.path/'AI_README.txt').write_text('Milo voice training: one speaker (Nitin), six commands, ten accepted WAVs each.\n'
          'WAV files are original 3-second, mono, 16kHz signed PCM16 clips from INMP441. Includes 200ms pre-roll; no trim, normalisation or augmentation.\n'
          'Use manifest.csv or manifest.jsonl. label is come/sit/paw/spin/bang/fetch; transcript is the full spoken phrase.\n'
          'Both glove throw styles map to the same spoken class fetch. No roll class.\n'
          'Labels are prompted and manually accepted, not recognised automatically; fast mode does not play recordings.\n'
          'Per-take JSON includes raw capture metadata, quality checks and WAV SHA256.\n'
          'Capture timestamps are mic uptime (device_monotonic_ms), not UTC. accepted_at_utc is the computer acceptance time.\n'
          'This is a small positive-command set, with no silence/unknown/other-speaker classes.\n'
          'For evaluation, prefer additional recordings from a later session; these takes alone do not establish accuracy.\n'
          'manifest.json includes counts and complete=false until all 60 examples are accepted.\n',encoding='utf-8')
        self.entries=self.load_entries();self.export()
    def load_entries(self):
        entries=[]
        for p in sorted((self.path/'commands').glob('*/*/metadata.json')):
            e=json.loads(p.read_text(encoding='utf-8'));wav=self.path/e['path']
            if e['label'] not in COMMANDS or not 1<=e['take']<=COUNT or wav.parent!=p.parent or not wav.is_file():raise ValueError('Invalid saved take: '+str(p))
            content=wav.read_bytes()
            if hashlib.sha256(content).hexdigest()!=e['sha256']:raise ValueError('Saved WAV hash mismatch: '+str(wav))
            with wave.open(io.BytesIO(content),'rb') as w:
                if (w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes())!=(16000,1,2,48000) or len(w.readframes(48000))!=96000:raise ValueError('Invalid saved WAV: '+str(wav))
            if any(x['label']==e['label'] and x['take']==e['take'] for x in entries):raise ValueError('Duplicate saved take')
            entries.append(e)
        return entries
    def pending(self):
        saved={(e['label'],e['take']) for e in self.entries}
        return next(((label,n) for label in COMMANDS for n in range(1,COUNT+1) if (label,n) not in saved),None)
    def accept(self,label,number,doc,wav,quality):
        if (label,number)!=self.pending():raise ValueError('Take is out of sequence or already accepted.')
        folder=self.path/'commands'/label/f'take_{number:02d}';folder.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path/('.pending_'+uuid.uuid4().hex);temp.mkdir()
        e={'path':(folder/'audio.wav').relative_to(self.path).as_posix(),'label':label,'transcript':'Milo '+label,
          'take':number,'speaker_id':'Nitin','sample_rate_hz':16000,'duration_s':3,'channels':1,
          'sha256':hashlib.sha256(wav).hexdigest(),'accepted_at_utc':datetime.now(timezone.utc).isoformat(),
          'capture_id':doc['data']['capture_id'],'quality':quality,'capture':doc}
        (temp/'audio.wav').write_bytes(wav);(temp/'metadata.json').write_text(json.dumps(e,indent=2)+'\n',encoding='utf-8')
        if folder.exists():raise FileExistsError('Existing take will not be overwritten.')
        temp.rename(folder);self.entries.append(e);self.export()
    def export(self):
        fields=['path','label','transcript','take','speaker_id','sample_rate_hz','duration_s','channels','sha256','capture_id','accepted_at_utc']
        temp=self.path/'manifest.csv.tmp'
        with temp.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:e[k] for k in fields} for e in self.entries)
        temp.replace(self.path/'manifest.csv')
        manifest={'schema':'milo-voice-training-v1','accepted_count':len(self.entries),'complete':self.pending() is None,
          'counts':{label:sum(e['label']==label for e in self.entries) for label in COMMANDS},'samples':self.entries}
        for name,body in [('manifest.json',json.dumps(manifest,indent=2)+'\n'),('manifest.jsonl',''.join(json.dumps(e)+'\n' for e in self.entries))]:
            p=self.path/(name+'.tmp');p.write_text(body,encoding='utf-8');p.replace(self.path/name)
        self.zip_path=self.path.parent/(self.path.name+'.zip');temp=self.zip_path.with_suffix('.zip.tmp')
        # Explicit allowlist excludes credentials, programs, rejected takes and unfinished transaction folders.
        paths=['session.json','AI_README.txt','manifest.csv','manifest.json','manifest.jsonl']
        for e in self.entries:paths += [e['path'],str(Path(e['path']).with_name('metadata.json'))]
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            for rel in paths:z.write(self.path/rel,Path(rel).as_posix())
        temp.replace(self.zip_path)
