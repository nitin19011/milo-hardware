Milo FAST voice collector - separate from the previous collector

FIRST: flash MicVoiceFast/MicVoiceFast.ino onto the MIC ESP32.
Board: FireBeetle-ESP32 (DFR0478), ESP32 core 3.3.11, ArduinoJson 7.x.
This new firmware removes the old ESP's built-in wait; changing only the desktop app is not enough.
Close the previous collector before launching this version. Leave the glove off.

Connect laptop + mic to the Nitin hotspot as before. Broker: 172.20.10.2:1883.
Run START_VOICE_COLLECTION.bat in THIS folder. SETUP_ONCE.bat is only needed if packages are missing.
The app uses the same broker address as the ESP and reuses your running local broker.

FAST WORKFLOW:
  Press Record (or Space), and say the displayed whole phrase immediately.
  No countdown, no automatic playback, no one-second post-recording delay.
  When the recording arrives, press Keep/Enter, or Retry if you misspoke or were interrupted.
  Next take stays on the same command until ten accepted takes are saved, then moves to the next command.
  There is no automatic acceptance: you still decide whether each take was good.

Commands: Milo come, Milo sit, Milo paw, Milo spin, Milo bang, Milo fetch.
Ten accepted recordings per command = 60 total. Both throwing styles share the spoken word fetch.
Each WAV is still 3 seconds, 16kHz mono signed PCM16 (48,000 samples).

The mic continuously keeps a small LOCAL history buffer while powered on. It does not stream that history.
On a capture request it includes 200ms before the request, plus the next approximately 2.8 seconds.
This pre-roll helps preserve your first syllable when speaking on the button press.
No silence padding or fabricated audio is added. Missing history/audio is rejected.
The complete WAV uploads as soon as its actual 3-second sample window is frozen.
MQTT confirmation round-trip time is recorded as a diagnostic, not used to infer missing speech.
A slow return acknowledgement can arrive after audio capture has already begun. Audio gaps remain rejected.

Session: voice-training-fast, source voice-mic-fast-01. Separate from the old voice collector and demo.
Only mic + laptop are needed; no public relay, NTP, internet clock, glove or motor.
Microphone wiring/gain and PCM format match the previous collector.

NEW SAVES:
  This folder/datasets/<session>/commands/<command>/take_01/audio.wav
  Each take has metadata.json, including capture_mode=fast_preroll_v1 and pre_roll_ms=200.
  The adjacent session ZIP updates on each Keep. Send THAT dataset ZIP to the AI teammate.
  Existing recordings in the previous folder are not copied, moved, overwritten or mixed automatically.
  To resume this new collection, select its session folder with Resume saved session.

The package contains your Wi-Fi setting. Dataset ZIPs exclude connection settings/code.
For the integrated demo, reflash Demo/MicDemo/MicDemo.ino. The original demo and collector files are untouched.
