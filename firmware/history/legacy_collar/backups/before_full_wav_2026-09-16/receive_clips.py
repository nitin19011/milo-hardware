"""Subscribe to Milo candidate packets; save only complete, CRC-checked WAVs."""
from pathlib import Path
import argparse
import json
import struct
import time
import wave
import zlib

ROOT=Path(__file__).resolve().parent

class ClipAssembler:
    def __init__(self, output):
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.pending={}
    def clear(self):
        self.pending.clear()
    def accept(self,topic,payload):
        if topic not in ('sensor/collar/voice/event','sensor/collar/voice/audio'):
            return
        now=time.monotonic()
        for k in list(self.pending):
            if now-self.pending[k]['time']>15:
                print(f'Discarded incomplete/timed-out clip {k}')
                del self.pending[k]
        if topic.endswith('/event'):
            event=json.loads(payload)
            if event.get('source_id')!='collar':
                return
            key=(int(event['session_id']),int(event['clip_id']))
            if event['type']=='wake_candidate':
                if len(self.pending)>=8: self.pending.pop(next(iter(self.pending)))
                self.pending[key]={'time':now,'frames':{},'event':event}
                print(f'Possible Milo: clip {key}, distance={event["distance"]:.4f}')
            elif event['type']=='voice_candidate':
                item=self.pending.pop(key,None)
                n=int(event['frames'])
                if not item or not event['complete'] or n<1 or n>200:
                    print(f'Discarded incomplete clip {key}');return
                if set(item['frames'])!=set(range(n)):
                    print(f'Discarded clip {key}: missing audio packets');return
                audio=b''.join(item['frames'][i] for i in range(n))
                if zlib.crc32(audio)!=int(event['crc32']):
                    print(f'Discarded clip {key}: CRC mismatch');return
                stem=f'{time.time_ns()}_{key[0]:08x}_{key[1]}'
                with wave.open(str(self.output/f'{stem}.wav'),'wb') as w:
                    w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(audio)
                (self.output/f'{stem}.json').write_text(json.dumps(event,indent=2))
                print(f'Saved {stem}.wav'+(' [time limit reached]' if event['truncated'] else ''))
        elif topic.endswith('/audio'):
            if len(payload)!=660 or payload[:4]!=b'MLA1':return
            session,clip,index,count=struct.unpack('<IIII',payload[4:20])
            key=(session,clip)
            if key in self.pending and count==320 and index<200:
                self.pending[key]['frames'][index]=payload[20:]

def main():
    import paho.mqtt.client as mqtt
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='172.20.10.2');parser.add_argument('--port',type=int,default=1883)
    args=parser.parse_args()
    assembler=ClipAssembler(ROOT/'received_clips')
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    def connect(c,u,flags,reason,properties):
        if reason.is_failure: print(f'Connection failed: {reason}');return
        assembler.clear();c.subscribe('sensor/collar/voice/#')
        print('Listening for candidate clips. Ctrl+C to stop.')
    def message(c,u,m):
        # Retained stale candidates must never be interpreted as new commands.
        if m.retain:return
        try: assembler.accept(m.topic,m.payload)
        except (ValueError,KeyError,TypeError,struct.error) as exc: print(f'Invalid packet: {exc}')
    client.on_connect=connect;client.on_message=message
    client.connect(args.host,args.port,keepalive=30)
    try: client.loop_forever()
    except KeyboardInterrupt: client.disconnect()

if __name__=='__main__':main()
