#include <Arduino.h>
#include <Wire.h>

#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_timer.h>
#include <esp_system.h>

// ============================================================
// USER SETTINGS
// ============================================================

const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";

const char MQTT_BROKER_IP[] = "172.20.10.2";

const uint16_t MQTT_BROKER_PORT = 1883;

#define DEVICE_ID "glove"

const char MOTION_TOPIC[]       = "sensor/glove/gesture";
const char CONNECTION_TOPIC[]   = "status/" DEVICE_ID "/connection";

const char CONNECTION_ONLINE_PAYLOAD[] =
    "{\"type\":\"connection_status\",\"state\":\"ONLINE\"}";

const char CONNECTION_OFFLINE_PAYLOAD[] =
    "{\"type\":\"connection_status\",\"state\":\"OFFLINE\"}";



const uint8_t MPU_ADDRESS = 0x68;

const int FLEX_THUMB_PIN  = 35;  // A3 -- physical wiring
const int FLEX_INDEX_PIN  = 34;  // A2
const int FLEX_MIDDLE_PIN = 39;  // A1

// Thresholds are 12-bit raw ADC counts
const uint16_t FLEX_THUMB_BENT_THRESHOLD  = 1500; // Mounted-glove fist low was 1612; straight releases stayed below 1401.
const uint16_t FLEX_INDEX_BENT_THRESHOLD  = 1800;
const uint16_t FLEX_MIDDLE_BENT_THRESHOLD = 1800;
// Set a finger to false if its readings DECREASE when bending.
const bool FLEX_THUMB_BEND_INCREASES  = true;
const bool FLEX_INDEX_BEND_INCREASES  = true;
const bool FLEX_MIDDLE_BEND_INCREASES = true;
const uint16_t FLEX_HYSTERESIS = 20; // Release margin in ADC counts and avoids flicker.
const bool PUBLISH_FLEX_RAW = true; // Set false after calibration

const uint32_t SAMPLE_PERIOD_MS       = 20;  // 50 Hz
const uint32_t MQTT_RETRY_MS          = 5000;

// ============================================================
// SAMPLE QUEUE
// ============================================================

// Main stream keeps the existing fields; collection labels and quality are additive.
const char COLLECTION_CONTROL_TOPIC[] = "collection/glove/control";
const char COLLECTION_ACK_TOPIC[] = "collection/glove/ack";
const char HARDWARE_PROFILE[] = "mpu6050_16g_2000dps_21hz_flex8avg_50hz_v1";
struct CollectionState {
  char session[17];
  uint16_t trial;
  uint64_t startUs, endUs;
};
CollectionState collectionState = {};
portMUX_TYPE collectionMux = portMUX_INITIALIZER_UNLOCKED;
char bootID[9];
bool imuConfigured = false;

struct SensorSample {
  uint32_t sequence;
  uint64_t timestampUs;

  float ax;
  float ay;
  float az;

  float gx;
  float gy;
  float gz;

  uint16_t thumb;
  uint16_t index;
  uint16_t middle;
  bool thumbBent;
  bool indexBent;
  bool middleBent;

  bool mpuValid;
  int16_t imuRaw[6];
  uint8_t flexRailMask;
  uint32_t imuErrors, queueDropped;
  char collectionSession[17];
  uint16_t collectionTrial;
  uint32_t collectionElapsedMs;
};

uint32_t imuErrorCount = 0;
uint32_t queueDropCount = 0;

bool readMPURegisters(uint8_t reg, uint8_t *buffer, uint8_t count) {
  Wire.beginTransmission(MPU_ADDRESS); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU_ADDRESS, count, true) != count) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint8_t i = 0; i < count; ++i) buffer[i] = Wire.read();
  return true;
}
bool writeMPURegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDRESS); Wire.write(reg); Wire.write(value);
  return Wire.endTransmission()==0;
}
bool configureMPU() {
  uint8_t who;
  if (!readMPURegisters(0x75,&who,1) || who!=0x68) return false;
  // Checked writes avoid an unbounded library reset-poll on a failing I2C bus.
  // +/-16 g, +/-2000 deg/s, 21 Hz DLPF; output data is sampled by this sketch at 50 Hz.
  if (!(writeMPURegister(0x6B,0x01) && writeMPURegister(0x6C,0x00) &&
        writeMPURegister(0x1A,0x04) && writeMPURegister(0x19,0x04) &&
        writeMPURegister(0x1B,0x18) && writeMPURegister(0x1C,0x18))) return false;
  uint8_t ranges[2];
  return readMPURegisters(0x1B,ranges,2) && (ranges[0]&0x18)==0x18 && (ranges[1]&0x18)==0x18;
}
bool readCheckedIMU(SensorSample &sample) {
  uint8_t bytes[14];
  if (!imuConfigured || !readMPURegisters(0x3B, bytes, sizeof(bytes))) return false;
  int16_t values[7];
  for (int i = 0; i < 7; ++i) values[i] = (int16_t)((uint16_t(bytes[2*i]) << 8) | bytes[2*i+1]);
  sample.imuRaw[0]=values[0]; sample.imuRaw[1]=values[1]; sample.imuRaw[2]=values[2];
  sample.imuRaw[3]=values[4]; sample.imuRaw[4]=values[5]; sample.imuRaw[5]=values[6];
  sample.ax=values[0]*9.80665f/2048.0f; sample.ay=values[1]*9.80665f/2048.0f; sample.az=values[2]*9.80665f/2048.0f;
  sample.gx=values[4]*0.01745329252f/16.4f; sample.gy=values[5]*0.01745329252f/16.4f; sample.gz=values[6]*0.01745329252f/16.4f;
  return true;
}


QueueHandle_t sampleQueue;

uint32_t sequenceNumber = 0;

// ============================================================
// NETWORK
// ============================================================

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

void collectionCommand(char *, byte *payload, unsigned int length) {
  if (length == 0 || length >= 100) return;
  char text[100], session[17], extra;
  memcpy(text,payload,length);text[length]='\0';
  unsigned int trial,duration;
  if (sscanf(text,"GO %16s %u %u %c",session,&trial,&duration,&extra)==3 &&
      strlen(session)==16 && trial>=1 && trial<=60000 && duration>=1000 && duration<=30000) {
    for (char *p=session;*p;++p) if (!isxdigit((unsigned char)*p)) return;
    uint64_t now=esp_timer_get_time();bool accepted;
    CollectionState snapshot;
    portENTER_CRITICAL(&collectionMux);
    if (!strcmp(session,collectionState.session) && trial==collectionState.trial) accepted=true;
    else if (now<collectionState.endUs) accepted=false;
    else {strcpy(collectionState.session,session);collectionState.trial=trial;
      collectionState.startUs=now;collectionState.endUs=now+uint64_t(duration)*1000;accepted=true;}
    snapshot=collectionState;
    portEXIT_CRITICAL(&collectionMux);
    char ack[230];
    snprintf(ack,sizeof(ack),"{\"boot\":\"%s\",\"session\":\"%s\",\"trial\":%u,\"accepted\":%s,\"start_us\":%llu,\"end_us\":%llu}",
      bootID,snapshot.session,snapshot.trial,accepted?"true":"false",
      (unsigned long long)snapshot.startUs,(unsigned long long)snapshot.endUs);
    mqtt.publish(COLLECTION_ACK_TOPIC,ack,false);
  } else if (sscanf(text,"STOP %16s %c",session,&extra)==1) {
    portENTER_CRITICAL(&collectionMux);
    if (!strcmp(session,collectionState.session)) collectionState.endUs=esp_timer_get_time();
    portEXIT_CRITICAL(&collectionMux);
  }
}

void forceMqttReconnect() {
  // Stop the TCP socket immediately. Do not call mqtt.disconnect()
  // here because it attempts another write on a possibly dead socket.
  wifiClient.stop();
  digitalWrite(LED_BUILTIN, LOW);
}

// ============================================================
// SENSOR FUNCTIONS
// ============================================================

int readFlex(int pin) {
  // Dummy read to let the ADC settle after changing channels. (discard one reading and allow settling)
  analogRead(pin);
  delayMicroseconds(200);
  uint32_t total = 0;
  for (int i = 0; i < 8; ++i) total += analogRead(pin); // average eight consecutive ADC readings per finger to reduce noise before applying the threshold
  return total / 8;
}


bool updateFlexBent(uint16_t reading, uint16_t threshold,
                           bool increases, uint16_t margin, bool wasBent) {
  const int value=reading, limit=threshold, gap=margin;
  if (increases) return wasBent ? value>=limit-gap : value>=limit;
  return wasBent ? value<=limit+gap : value<=limit;
}

const char *flexState(bool bent) {
  return bent ? "BENT" : "NOT_BENT";
}

// ============================================================
// MQTT PUBLISHING
// ============================================================

bool publishSensorSample(const SensorSample &sample) {
  char payload[1100];
  char extraFields[620];
  snprintf(extraFields,sizeof(extraFields),
    ",\"boot_id\":\"%s\",\"hardware_profile\":\"%s\",\"sample_hz\":50,\"accel_range_g\":16,\"gyro_range_deg_s\":2000,"
    "\"imu_raw\":[%d,%d,%d,%d,%d,%d],\"quality\":{\"flex_rail_mask\":%u,\"imu_errors\":%lu,\"queue_dropped\":%lu},"
    "\"collection\":{\"session\":\"%s\",\"trial\":%u,\"elapsed_ms\":%lu},\"rssi_dbm\":%d",
    bootID,HARDWARE_PROFILE,sample.imuRaw[0],sample.imuRaw[1],sample.imuRaw[2],sample.imuRaw[3],sample.imuRaw[4],sample.imuRaw[5],
    sample.flexRailMask,(unsigned long)sample.imuErrors,(unsigned long)sample.queueDropped,sample.collectionSession,
    sample.collectionTrial,(unsigned long)sample.collectionElapsedMs,WiFi.RSSI());
  char rawFields[100] = "";
  if (PUBLISH_FLEX_RAW) {
    snprintf(rawFields, sizeof(rawFields),
      ",\"flex_raw\":{\"thumb\":%u,\"index\":%u,\"middle\":%u}",
      unsigned(sample.thumb), unsigned(sample.index), unsigned(sample.middle));
  }

  int length = snprintf(
    payload,
    sizeof(payload),
    "{"
      "\"type\":\"hand_sample\","
      "\"seq\":%lu,"
      "\"timestamp_us\":%llu,"
      "\"imu\":{"
        "\"ax\":%.3f,"
        "\"ay\":%.3f,"
        "\"az\":%.3f,"
        "\"gx\":%.3f,"
        "\"gy\":%.3f,"
        "\"gz\":%.3f,"
        "\"valid\":%s"
      "},"
      "\"flex\":{"
        "\"thumb\":\"%s\","
        "\"index\":\"%s\","
        "\"middle\":\"%s\""
      "}%s%s"
    "}",
    (unsigned long)sample.sequence,
    (unsigned long long)sample.timestampUs,
    sample.ax,
    sample.ay,
    sample.az,
    sample.gx,
    sample.gy,
    sample.gz,
    sample.mpuValid ? "true" : "false",
    flexState(sample.thumbBent),
    flexState(sample.indexBent),
    flexState(sample.middleBent),
    rawFields,
    extraFields
  );

  if (length <= 0 || length >= (int)sizeof(payload)) {
    return false;
  }

  return mqtt.publish(
    MOTION_TOPIC,
    reinterpret_cast<const uint8_t *>(payload),
    length,
    false
  );
}

// ============================================================
// NETWORK TASK
// Runs separately so reconnection does not stop 50 Hz sampling.
// ============================================================

void networkTask(void *parameter) {
  uint32_t wifiAttemptStarted = 0;
  uint32_t lastMqttAttempt = 0;
  uint32_t lastStatusPrint = 0;
  uint32_t lastLedToggle = 0;

  bool previousWiFiConnected = false;
  bool ledState = false;

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);

  // Reliability-first setting for this test.
  WiFi.setSleep(false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  mqtt.setCallback(collectionCommand);
  if (!mqtt.setBufferSize(1536)) {
    Serial.println("# ERROR: MQTT buffer allocation failed");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  // Detect a dead broker connection within roughly 5-10 seconds.
  mqtt.setKeepAlive(5);
  mqtt.setSocketTimeout(1);

  // Start the first Wi-Fi attempt immediately.
  Serial.println("# Starting Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  wifiAttemptStarted = millis();

  for (;;) {
    uint32_t now = millis();
    bool wifiConnected =
        WiFi.status() == WL_CONNECTED;

    if (!wifiConnected) {
      if (previousWiFiConnected) {
        previousWiFiConnected = false;
        forceMqttReconnect();
      }

      // Fast LED blink: Wi-Fi is disconnected.
      if (now - lastLedToggle >= 250) {
        lastLedToggle = now;
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
      }

      // Print diagnostic status every five seconds.
      if (now - lastStatusPrint >= 5000) {
        lastStatusPrint = now;

        Serial.print("# Wi-Fi waiting, status=");
        Serial.println(WiFi.status());
      }

      // Give each attempt 20 seconds before restarting it.
      if (now - wifiAttemptStarted >= 20000) {
        Serial.println("# Restarting Wi-Fi attempt");

        WiFi.disconnect(false);
        vTaskDelay(pdMS_TO_TICKS(250));

        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        wifiAttemptStarted = millis();
      }
    } else {
      if (!previousWiFiConnected) {
        previousWiFiConnected = true;

        // Wi-Fi may have recovered while an old TCP socket remained.
        // Always begin this Wi-Fi session with a clean MQTT transport.
        forceMqttReconnect();

        Serial.print("# Wi-Fi connected, IP=");
        Serial.println(WiFi.localIP());

        Serial.print("# Wi-Fi RSSI=");
        Serial.println(WiFi.RSSI());

        // Permit an immediate MQTT attempt.
        lastMqttAttempt = now - MQTT_RETRY_MS;
      }

      if (!mqtt.connected()) {
        // Slow LED blink: Wi-Fi works, MQTT does not.
        if (now - lastLedToggle >= 1000) {
          lastLedToggle = now;
          ledState = !ledState;
          digitalWrite(LED_BUILTIN, ledState);
        }

        if (now - lastMqttAttempt >= MQTT_RETRY_MS) {
          lastMqttAttempt = now;

          String clientId =
              String(DEVICE_ID) + "-" +
              String(
                (uint32_t)ESP.getEfuseMac(),
                HEX
              );

          Serial.print("# MQTT connection attempt to ");
          Serial.println(MQTT_BROKER_IP);

          if (mqtt.connect(
                clientId.c_str(),
                CONNECTION_TOPIC,
                1,
                true,
                CONNECTION_OFFLINE_PAYLOAD)) {

            if (mqtt.subscribe(COLLECTION_CONTROL_TOPIC,1) && mqtt.publish(
                  CONNECTION_TOPIC,
                  CONNECTION_ONLINE_PAYLOAD,
                  true)) {

              // Offline samples are stale by the time the link returns.
              xQueueReset(sampleQueue);


              Serial.println("# MQTT connected");
            } else {
              Serial.println("# MQTT online publish failed");
              forceMqttReconnect();
            }
          } else {
            Serial.print("# MQTT failed, state=");
            Serial.println(mqtt.state());
          }
        }
      } else {
        // mqtt.loop() detects keep-alive and broker failures.
        // A failure must close the socket so the next pass reconnects.
        if (!mqtt.loop()) {
          forceMqttReconnect();
          vTaskDelay(pdMS_TO_TICKS(20));
          continue;
        }

        // Publish at most one sample per task pass. The task runs every
        // 2 ms while samples arrive every 20 ms, so this keeps up without
        // issuing a burst of blocking writes after a link failure.
        SensorSample sample;

        if (xQueueReceive(
              sampleQueue,
              &sample,
              0) == pdTRUE) {

          if (!publishSensorSample(sample)) {
            forceMqttReconnect();
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
          }
        }

        // Solid LED only after this pass completed successfully.
        digitalWrite(LED_BUILTIN, HIGH);
        ledState = true;
      }
    }

    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Wire.begin(21, 22); // starts I2C
  Wire.setClock(100000); // i2c digital bus speed 100k
  Wire.setTimeOut(20);
  snprintf(bootID,sizeof(bootID),"%08lx",(unsigned long)esp_random());

  analogReadResolution(12); // adc using 12 bits, counter from 0 to 4095

  analogSetPinAttenuation( // allow the ADC to measure wider input voltages
    FLEX_THUMB_PIN,
    ADC_11db
  );

  analogSetPinAttenuation(
    FLEX_INDEX_PIN,
    ADC_11db
  );

  analogSetPinAttenuation(
    FLEX_MIDDLE_PIN,
    ADC_11db
  );


  pinMode(FLEX_THUMB_PIN, INPUT); // set the pins as inputs
  pinMode(FLEX_INDEX_PIN, INPUT);
  pinMode(FLEX_MIDDLE_PIN, INPUT);

  imuConfigured=configureMPU();
  if (!imuConfigured) Serial.println("# MPU unavailable; publishing invalid readings and retrying without blocking Wi-Fi.");

  sampleQueue =
      xQueueCreate(100, sizeof(SensorSample));

  if (sampleQueue == nullptr) {
    Serial.println("# ERROR: sample queue creation failed");

    while (true) {
      delay(100);
    }
  }

  Serial.println("# Glove IMU/flex MQTT ready (microphone moved to collar)");
  Serial.println("# Flex pins: thumb=GPIO35 index=GPIO34 middle=GPIO39");
  Serial.printf("# CALIBRATE: thresholds thumb=%u index=%u middle=%u; release margin=%u\n",
    unsigned(FLEX_THUMB_BENT_THRESHOLD), unsigned(FLEX_INDEX_BENT_THRESHOLD),
    unsigned(FLEX_MIDDLE_BENT_THRESHOLD), unsigned(FLEX_HYSTERESIS));
  Serial.println(
    "# seq,time_us,ax,ay,az,gx,gy,gz,"
    "thumb_raw,index_raw,middle_raw,thumb_state,index_state,middle_state; IMU units m/s^2 and rad/s"
  );

  if (xTaskCreatePinnedToCore(
        networkTask,
        "networkTask",
        8192,
        nullptr,
        1,
        nullptr,
        0) != pdPASS) {
    Serial.println("# ERROR: network task creation failed");
    while (true) {
      delay(100);
    }
  }

  if (xTaskCreatePinnedToCore(
        sensorTask,
        "sensorTask",
        4096,
        nullptr,
        2,
        nullptr,
        1) != pdPASS) {
    Serial.println("# ERROR: sensor task creation failed");
    while (true) {
      delay(100);
    }
  }
}

// ============================================================
// 50 HZ SENSOR TASK
// ============================================================

void sensorTask(void *parameter) {
  // State belongs to this task and travels with its sampled readings in the queue.
  bool thumbBent=false, indexBent=false, middleBent=false;
  uint32_t lastMPURetry=millis();
  TickType_t lastWakeTime = xTaskGetTickCount();
  const TickType_t samplePeriod =
      pdMS_TO_TICKS(SAMPLE_PERIOD_MS);

  for (;;) {
    vTaskDelayUntil(&lastWakeTime, samplePeriod);

    SensorSample sample = {};
    sample.sequence=sequenceNumber++;
    sample.timestampUs=esp_timer_get_time();
    CollectionState capture;
    portENTER_CRITICAL(&collectionMux);capture=collectionState;portEXIT_CRITICAL(&collectionMux);
    memcpy(sample.collectionSession,capture.session,sizeof(sample.collectionSession));
    if (capture.trial && sample.timestampUs>=capture.startUs && sample.timestampUs<capture.endUs) {
      sample.collectionTrial=capture.trial;sample.collectionElapsedMs=(sample.timestampUs-capture.startUs)/1000;
    }
    if (!imuConfigured && millis()-lastMPURetry>=2000) {lastMPURetry=millis();imuConfigured=configureMPU();}
    // Checked burst read replaces the old unconditional Adafruit getEvent valid flag.
    bool mpuReadOk=readCheckedIMU(sample);
    if (!mpuReadOk) {++imuErrorCount;imuConfigured=false;}
    sample.imuErrors=imuErrorCount;sample.queueDropped=queueDropCount;

    sample.thumb  = readFlex(FLEX_THUMB_PIN);
    sample.index  = readFlex(FLEX_INDEX_PIN);
    sample.middle = readFlex(FLEX_MIDDLE_PIN);
    // Preserve raw fault evidence. Do not turn an ADC rail spike into a bend transition.
    sample.flexRailMask=(sample.thumb<=20 || sample.thumb>=4075 ? 1 : 0) |
                        (sample.index<=20 || sample.index>=4075 ? 2 : 0) |
                        (sample.middle<=20 || sample.middle>=4075 ? 4 : 0);
    if (!(sample.flexRailMask & 1)) thumbBent = updateFlexBent(sample.thumb, FLEX_THUMB_BENT_THRESHOLD,
      FLEX_THUMB_BEND_INCREASES, FLEX_HYSTERESIS, thumbBent);
    if (!(sample.flexRailMask & 2)) indexBent = updateFlexBent(sample.index, FLEX_INDEX_BENT_THRESHOLD,
      FLEX_INDEX_BEND_INCREASES, FLEX_HYSTERESIS, indexBent);
    if (!(sample.flexRailMask & 4)) middleBent = updateFlexBent(sample.middle, FLEX_MIDDLE_BENT_THRESHOLD,
      FLEX_MIDDLE_BEND_INCREASES, FLEX_HYSTERESIS, middleBent);
    sample.thumbBent = thumbBent;
    sample.indexBent = indexBent;
    sample.middleBent = middleBent;
    sample.mpuValid = mpuReadOk;


    // Never block sensor sampling because of networking.
    if (xQueueSend(sampleQueue, &sample, 0) != pdTRUE) {
      SensorSample discarded;

      // Real-time motion data should keep the newest sample.
      if (xQueueReceive(sampleQueue, &discarded, 0)==pdTRUE) ++queueDropCount;
      sample.queueDropped=queueDropCount;
      xQueueSend(sampleQueue, &sample, 0);
    }

    // Five updates/second makes calibration visible without printing at 50 Hz.
    if (sample.sequence % 10 == 0) {
      Serial.print(sample.sequence);
      Serial.print(",");
      Serial.print(
        (unsigned long long)sample.timestampUs
      );

      Serial.print(",");
      Serial.print(sample.ax, 3);
      Serial.print(",");
      Serial.print(sample.ay, 3);
      Serial.print(",");
      Serial.print(sample.az, 3);

      Serial.print(",");
      Serial.print(sample.gx, 3);
      Serial.print(",");
      Serial.print(sample.gy, 3);
      Serial.print(",");
      Serial.print(sample.gz, 3);

      Serial.print(",");
      Serial.print(sample.thumb);
      Serial.print(",");
      Serial.print(sample.index);
      Serial.print(",");
      Serial.print(sample.middle);
      Serial.print(",");
      Serial.print(flexState(sample.thumbBent));
      Serial.print(",");
      Serial.print(flexState(sample.indexBent));
      Serial.print(",");
      Serial.print(flexState(sample.middleBent));

      Serial.println();
    }
  }
}

void loop() {
  // Sensor and networking work runs in dedicated FreeRTOS tasks.
  vTaskDelay(pdMS_TO_TICKS(1000));
}
