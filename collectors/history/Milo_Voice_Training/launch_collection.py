"""Reuse the laptop broker, or start the installed Mosquitto for this collection run."""
import json,shutil,socket,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def listening(host,port):
    try:
        with socket.create_connection((host,port),timeout=.4):return True
    except OSError:return False
def main():
    c=json.loads((ROOT/'voice_settings.local.json').read_text(encoding='utf-8-sig'))
    host=c['mqtt_host'];port=c['mqtt_port'];broker=None;log=None
    try:
        if not listening(host,port):
            candidates=[shutil.which('mosquitto'),r'C:\Users\nitin\OneDrive\NUS\Y3S1\CG4002 Computer Engineering Capstone Project\Mosquitto\mosquitto.exe',r'C:\Program Files\mosquitto\mosquitto.exe']
            exe=next((p for p in candidates if p and Path(p).is_file()),None)
            if not exe:raise RuntimeError('Start your laptop Mosquitto broker on port 1883, then launch again.')
            if port!=1883:raise RuntimeError('Start the broker on the configured port separately.')
            try:
                with socket.socket() as probe:probe.bind((host,0))
            except OSError:raise RuntimeError('The configured broker address is not on this laptop. Check its hotspot IP.')
            log=(ROOT/'local_broker.log').open('ab')
            broker=subprocess.Popen([exe,'-c',str(ROOT/'broker-local.conf')],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for _ in range(30):
                if listening(host,port):break
                if broker.poll() is not None:raise RuntimeError('Mosquitto stopped. See local_broker.log.')
                time.sleep(.1)
            else:raise RuntimeError('Laptop broker did not start; see local_broker.log.')
            print('Laptop broker started for this run.')
        else:print('Using your existing laptop broker.')
        from collect_voice import App
        import tkinter as tk
        root=tk.Tk();App(root);root.mainloop()
    finally:
        # Leave any pre-existing broker alone. Only stop the child we started ourselves.
        if broker:
            broker.terminate()
            try:broker.wait(timeout=4)
            except subprocess.TimeoutExpired:broker.kill();broker.wait(timeout=2)
        if log:log.close()
if __name__=='__main__':
    try:main()
    except Exception as e:print('Cannot start collection:',e);raise SystemExit(1)
