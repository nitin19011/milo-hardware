WIRELESS GUIDED GLOVE TEST

Checks the three flex sensors and MPU-6050 on your assembled glove.
Use battery power during all exercises. Haptics and the collar mic are outside this test.

1. CHECK YOUR NETWORK
Use your existing Wi-Fi/hotspot and MQTT broker. The sketch copies the network settings from MBF_v1.
The last configured broker IPv4 is 172.20.10.2, port 1883.
Check the laptop IPv4. If it changed, edit MQTT_BROKER_IP in the diagnostic sketch before uploading.

2. UPLOAD ONCE
Open Glove_Wireless_Test/Glove_Wireless_Test.ino in Arduino IDE.
Use the same FireBeetle-ESP32 board and USB port as your working glove.
Required external library: original PubSubClient (2.8 installed locally).
Wire, WiFi and ESP32 utilities come with the ESP32 board package.
Upload once over USB, then disconnect USB and run the glove from its battery.
Your original MBF_v1.ino was not edited; restore it after the diagnostic test.
LED: fast blink = Wi-Fi missing; slow blink = MQTT missing; solid = connected.

3. START THE BROKER
Use the working Mosquitto folder:
C:\Users\nitin\OneDrive\NUS\Y3S1\CG4002 Computer Engineering Capstone Project\Mosquitto
From that folder run: mosquitto.exe -c mosquitto-dev.conf -v
If the correct broker is already running, leave it running.

4. RUN THE LAPTOP GUIDE
Extract the package. Open a terminal in the extracted Glove_Wireless_Test folder.
Install the receiver dependency if needed:
  py -m pip install -r requirements.txt
Run with the CURRENT broker IPv4:
  py guided_glove_test.py --host 172.20.10.2 --speak
Or double-click Run_Glove_Test.bat; it uses 172.20.10.2 by default.
For another address: Run_Glove_Test.bat --host YOUR_CURRENT_IP
Omit --speak for text-only prompts. Speech uses the laptop speakers.
Keep the laptop awake, with this program and the broker running.

5. FOLLOW THE EXERCISES
Wear the glove normally. Read/listen to each instruction and press Enter when ready.
Get into position during the 3-second countdown. Follow the instruction for the recording period.
Beeps mark the start and end; the laptop displays remaining time.
Isolated bends: keep other fingers and wrist as still as possible.
Cycle trials: straight for 2 seconds, bent for 2 seconds, repeated three times.
IMU trials: still palm-up, palm-down, hand-on-edge, then controlled wrist/forearm movements.
Use comfortable motions and do not force the flex sensors.
There are 19 trials with about 3 minutes of recording; allow 5-10 minutes including preparation.

6. SEND THE RESULT
The program saves a new ZIP under test_results and prints its exact location.
Send that RESULT ZIP for review, rather than the software package.
Files inside:
  samples.csv: session readings and trial labels.
  raw_samples.jsonl: original decoded MQTT samples and receive timestamps.
  events.jsonl: commands, acknowledgements, connection events and completion state.
  manifest.json: plan, session, units and complete/partial state.
  summary.json: per-trial statistics, finger changes, cross-talk and data-quality flags.

DATA DETAILS
50 Hz sampling. Flex: 12-bit ADC, eight readings averaged after a settling delay.
No old bend thresholds are used to decide whether a sensor works; raw readings are recorded.
MPU: checked 14-byte I2C read, acceleration in m/s^2, angular velocity in rad/s.
Ranges/filter match the working glove: +/-4 g, +/-500 degrees/s, 21 Hz filter.
Register reference:
https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map.pdf

ESP-side trial tags prevent delayed network messages being assigned to the wrong action.
Repeated GO commands do not restart a trial. Trial duration is bounded to at most 30 seconds.
The 100-sample queue discards oldest samples when full; drop counters and sequence gaps are recorded.
MQTT data uses QoS 0: lost samples are reported, not recovered.
A reset or more than 3 seconds without live samples stops the test and saves a partial ZIP.
Under 90% of expected samples, near-rail ADC readings, failed IMU reads and IMU clipping are flagged.
The summary provides screening evidence; interpreting whether all sensors make sense needs review.

The sketch contains your copied Wi-Fi credentials. The result ZIP does not include the sketch/password.
