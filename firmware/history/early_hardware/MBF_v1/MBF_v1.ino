#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_timer.h>

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


Adafruit_MPU6050 mpu;

const uint8_t MPU_ADDRESS = 0x68;

const int FLEX_THUMB_PIN  = 35;  // A3 -- physical wiring
const int FLEX_INDEX_PIN  = 34;  // A2
const int FLEX_MIDDLE_PIN = 39;  // A1

// Thresholds are 12-bit raw ADC counts
const uint16_t FLEX_THUMB_BENT_THRESHOLD  = 1600;
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
};

QueueHandle_t sampleQueue;

uint32_t sequenceNumber = 0;

// ============================================================
// NETWORK
// ============================================================

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

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
  char payload[512];
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
      "}%s"
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
    rawFields
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
  if (!mqtt.setBufferSize(768)) {
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

            if (mqtt.publish(
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

  if (!mpu.begin(MPU_ADDRESS, &Wire)) {
    Serial.println("# ERROR: MPU-6050 not detected");

    while (true) {
      delay(100);
    }
  }

  // mpu configuration
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

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
  TickType_t lastWakeTime = xTaskGetTickCount();
  const TickType_t samplePeriod =
      pdMS_TO_TICKS(SAMPLE_PERIOD_MS);

  for (;;) {
    vTaskDelayUntil(&lastWakeTime, samplePeriod);

    sensors_event_t accel;
    sensors_event_t gyro;
    sensors_event_t temperature;

    // Adafruit getEvent() returns true unconditionally in the installed library.
    // Existing valid flag does NOT detect I2C transport failures; see SPLIT_NOTES.md.
    bool mpuReadOk =
        mpu.getEvent(&accel, &gyro, &temperature);

    SensorSample sample;

    sample.sequence = sequenceNumber++;
    sample.timestampUs = esp_timer_get_time();

    if (mpuReadOk) {
      sample.ax = accel.acceleration.x;
      sample.ay = accel.acceleration.y;
      sample.az = accel.acceleration.z;

      sample.gx = gyro.gyro.x;
      sample.gy = gyro.gyro.y;
      sample.gz = gyro.gyro.z;
    } else {
      sample.ax = 0.0f;
      sample.ay = 0.0f;
      sample.az = 0.0f;

      sample.gx = 0.0f;
      sample.gy = 0.0f;
      sample.gz = 0.0f;
    }

    sample.thumb  = readFlex(FLEX_THUMB_PIN);
    sample.index  = readFlex(FLEX_INDEX_PIN);
    sample.middle = readFlex(FLEX_MIDDLE_PIN);
    thumbBent = updateFlexBent(sample.thumb, FLEX_THUMB_BENT_THRESHOLD,
      FLEX_THUMB_BEND_INCREASES, FLEX_HYSTERESIS, thumbBent);
    indexBent = updateFlexBent(sample.index, FLEX_INDEX_BENT_THRESHOLD,
      FLEX_INDEX_BEND_INCREASES, FLEX_HYSTERESIS, indexBent);
    middleBent = updateFlexBent(sample.middle, FLEX_MIDDLE_BENT_THRESHOLD,
      FLEX_MIDDLE_BEND_INCREASES, FLEX_HYSTERESIS, middleBent);
    sample.thumbBent = thumbBent;
    sample.indexBent = indexBent;
    sample.middleBent = middleBent;
    sample.mpuValid = mpuReadOk;


    // Never block sensor sampling because of networking.
    if (xQueueSend(sampleQueue, &sample, 0) != pdTRUE) {
      SensorSample discarded;

      // Real-time motion data should keep the newest sample.
      xQueueReceive(sampleQueue, &discarded, 0);
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
