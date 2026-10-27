"""Console prompts and short cues; speech finishes before recording begins."""
import base64,subprocess
from datetime import datetime,timezone

def utc_now():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def beep():
    try:
        import winsound
        winsound.Beep(1000,80)
    except (ImportError,RuntimeError):pass

def announce(text,speak=False):
    print(text,flush=True)
    if not speak:return
    payload=base64.b64encode(text.encode('utf-8')).decode('ascii')
    code="Add-Type -AssemblyName System.Speech; $v=New-Object System.Speech.Synthesis.SpeechSynthesizer; $v.Speak([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+payload+"')))"
    encoded=base64.b64encode(code.encode('utf-16le')).decode('ascii')
    try:subprocess.run(['powershell','-NoProfile','-EncodedCommand',encoded],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    except (OSError,subprocess.SubprocessError):print('Use the displayed prompt; spoken prompts unavailable.')
