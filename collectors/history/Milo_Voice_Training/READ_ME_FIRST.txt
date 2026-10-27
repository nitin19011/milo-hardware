Milo wireless voice collection - YOUR LAPTOP BROKER

1. Flash MicVoiceTraining/MicVoiceTraining.ino onto the MIC ESP32.
   Board: FireBeetle-ESP32 (DFR0478), ESP32 core 3.3.11, ArduinoJson 7.x.
2. Connect your laptop and mic ESP to the same Nitin hotspot. The glove stays OFF.
   Laptop address: 172.20.10.2, MQTT port 1883, anonymous local connection (same as previous collection).
3. Run SETUP_ONCE.bat only if the Python packages are missing.
4. Run START_VOICE_COLLECTION.bat. It reuses your running laptop broker, or starts your installed
   Mosquitto with the matching local listener if no broker is running.
   A broker it starts itself is stopped when the collector closes; an existing broker is left running.
5. Power the mic by battery and disconnect USB. Wait for Mic ready in the collector.
6. Press Record. At the green GO, say the displayed WHOLE phrase once. Listen to playback.
   Keep advances to the next take; Retry does not save or count. All 10 takes of a command are sequential.

Six spoken labels, 10 accepted takes each:
  Milo come, Milo sit, Milo paw, Milo spin, Milo bang, Milo fetch.
Both throwing styles use the same spoken label fetch. No roll class.
Each WAV: exactly 3 seconds, 48,000 samples, 16kHz mono signed PCM16.
No trim, normalisation, speech recognition, glove trigger or motor is used.
Wear the microphone where you will wear it in the demo. Speak naturally; no gesture is needed.
INMP441 wiring: BCLK14, WS17, SD16, VDD3V3, GND and L/R to GND.

The DESKTOP collector controls the microphone directly through your local broker.
The ESP records using a relative timer and returns a remaining-time countdown. No NTP, public relay,
TLS certificate, internet time or shared clock is required for this voice-only collection.
The visible GO can be slightly late by the local return-message delay. Say the phrase promptly;
listen for complete words before keeping it. ESP metadata explicitly uses device_monotonic_ms,
while accepted_at_utc is the computer's acceptance time. Do not treat device uptime as a UTC timestamp.

Data: datasets/<session>/commands/<label>/take_01/audio.wav plus metadata.json.
manifest.csv, manifest.json and manifest.jsonl contain labels, transcripts, paths, counts and checksums.
The adjacent <session>.zip updates after EVERY accepted take. Send that DATASET ZIP to your AI teammate.
complete=true only when all 60 takes are accepted. Rejected/unaccepted recordings are not exported.
Resume saved session: choose the folder containing session.json. Earlier accepted takes are not overwritten.

If the mic does not connect:
  Check both devices are on the same hotspot and laptop still has address 172.20.10.2.
  Allow the existing Mosquitto application through Windows Firewall for the current local network if prompted.
  Do not run two brokers on port 1883. An existing authenticated broker needs matching credentials in settings.
  Broker startup details, if any, are in local_broker.log.
If the laptop IP/Wi-Fi changes: edit voice_settings.local.json, run CONFIGURE_VOICE.bat and reflash the mic.
Both desktop and ESP use mqtt_host=172.20.10.2. Do not substitute localhost/127.0.0.1 for the desktop:
different listeners on this laptop can lead to separate brokers. The app displays the address it uses.

This is temporary data collection firmware. Reflash Demo/MicDemo/MicDemo.ino for the integrated demo.
The demo files and public-broker settings have not been changed.
The collection PACKAGE contains your private Wi-Fi setting. Send the generated DATASET ZIP, not this package.
