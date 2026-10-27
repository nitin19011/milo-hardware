"""Save each collar MQTT WAV message directly; no audio-chunk assembly."""
from pathlib import Path
import argparse
import json
import re
import struct

ROOT = Path(__file__).resolve().parent
WAV_TOPIC = re.compile(r'^sensor/collar/voice/wav/([0-9a-f]{8})/([1-9][0-9]{0,9})$')
MAX_WAV_BYTES = 128044


def validate_wav(payload):
    if not 44 < len(payload) <= MAX_WAV_BYTES:
        raise ValueError('WAV length outside the configured four-second maximum')
    values = struct.unpack('<4sI4s4sIHHIIHH4sI', payload[:44])
    size = len(payload)-44
    expected = (b'RIFF',len(payload)-8,b'WAVE',b'fmt ',16,1,1,16000,32000,2,16,b'data',size)
    if values != expected or size % 640:
        raise ValueError('Invalid/incomplete collar WAV header, audio format or frame length')
    return size / 32000


class WavReceiver:
    def __init__(self, output):
        self.output=Path(output)
        self.output.mkdir(parents=True,exist_ok=True)

    def destination(self, topic):
        match=WAV_TOPIC.fullmatch(topic)
        if not match:
            return None
        return self.output/f'{match[1]}_{match[2]}.wav'

    def accept(self, topic, payload):
        path=self.destination(topic)
        if path is not None:
            duration=validate_wav(payload)
            if path.exists():
                if path.read_bytes()!=payload:
                    raise ValueError('Clip ID collision with different WAV data; refusing overwrite')
                print(f'Ignored duplicate {path.name}')
                return None
            with path.open('xb') as f:
                f.write(payload)  # EXACT bytes received, including the ESP-created WAV header.
            print(f'Saved {path.name}: {duration:.2f} s, {len(payload)} bytes')
            return path
        if topic=='sensor/collar/voice/event':
            if len(payload)>2048:
                raise ValueError('Oversized metadata')
            event=json.loads(payload)
            if not isinstance(event,dict):
                raise ValueError('Metadata must be an object')
            if event.get('schema_version')!=2 or event.get('source_id')!='collar':
                return None
            wav_topic=event.get('wav_topic')
            if not isinstance(wav_topic,str):
                return None
            path=self.destination(wav_topic)
            if path and path.exists():
                if event.get('wav_bytes')!=path.stat().st_size:
                    raise ValueError('Metadata does not match saved WAV size')
                path.with_suffix('.json').write_text(json.dumps(event,indent=2),encoding='utf-8')
                if event.get('truncated'):
                    print(f'WARNING: {path.name} hit the capture time limit; speech may be cut off')
        return None


def main():
    import paho.mqtt.client as mqtt
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='Broker IPv4; use 127.0.0.1 only on the broker PC')
    parser.add_argument('--port',type=int,default=1883)
    parser.add_argument('--output',default=str(ROOT/'received_wavs'))
    args=parser.parse_args()
    receiver=WavReceiver(args.output)
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    def connect(c,u,flags,reason,properties):
        if reason.is_failure:
            print(f'Connection failed: {reason}');return
        c.subscribe([('sensor/collar/voice/wav/#',0),('sensor/collar/voice/event',0)])
        print('Waiting for complete WAV messages. Ctrl+C to stop.')
    def message(c,u,m):
        if m.retain: return  # Never treat stale retained commands as new audio.
        try:
            receiver.accept(m.topic,m.payload)
        except (ValueError,TypeError,KeyError,OSError,struct.error) as exc:
            print(f'Rejected message/save failed: {exc}')
    client.on_connect=connect;client.on_message=message
    client.connect(args.host,args.port,keepalive=30)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__=='__main__': main()
