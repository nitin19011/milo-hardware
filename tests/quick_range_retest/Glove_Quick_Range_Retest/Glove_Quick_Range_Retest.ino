#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_timer.h>
#include <esp_system.h>

// Network settings copied from your working glove sketch.
// Recheck the broker IPv4 if your laptop/network has changed.
const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";
const char MQTT_BROKER_IP[] = "172.20.10.2";
const uint16_t MQTT_BROKER_PORT = 1883;

const int THUMB_PIN = 35;   // A3
const int INDEX_PIN = 34;   // A2
const int MIDDLE_PIN = 39;  // A1
const uint8_t MPU_ADDRESS = 0x68;
const char DATA_TOPIC[] = "diagnostic/glove/data";
const char CONTROL_TOPIC[] = "diagnostic/glove/control";
const char ACK_TOPIC[] = "diagnostic/glove/ack";
const char STATUS_TOPIC[] = "diagnostic/glove/status";

struct FlexReading { uint16_t mean, low, high; };
struct Sample {
  uint32_t seq, queueDropped, imuErrors;
  uint64_t us;
  char session[17];
  uint16_t trial;
  uint32_t elapsedMs;
  FlexReading thumb, index, middle;
  bool imuOK;
  int16_t raw[7]; // ax, ay, az, temperature, gx, gy, gz
};
struct TrialState {
  char session[17];
  uint16_t trial;
  uint64_t startUs, endUs;
};
TrialState state = {};
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
QueueHandle_t samples;
WiFiClient transport;
PubSubClient mqtt(transport);
char bootID[9];
uint32_t queueDropped = 0;

// Checked reads let the test distinguish I2C faults from real movement.
bool readRegisters(uint8_t reg, uint8_t *buffer, uint8_t count) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU_ADDRESS, count, true) != count) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint8_t i = 0; i < count; ++i) buffer[i] = Wire.read();
  return true;
}
bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDRESS);
  Wire.write(reg); Wire.write(value);
  return Wire.endTransmission() == 0;
}
bool initialiseIMU() {
  uint8_t id;
  if (!readRegisters(0x75, &id, 1) || id != 0x68) return false;
  // Expanded diagnostic ranges; unchanged 21 Hz filter and sample schedule.
  if (!(writeRegister(0x6B, 0x01) && writeRegister(0x1A, 0x04) &&
        writeRegister(0x19, 0x04) && writeRegister(0x1B, 0x18) &&
        writeRegister(0x1C, 0x10))) return false;
  uint8_t config[2];
  // Verify that both range registers really accepted the requested settings.
  return readRegisters(0x1B, config, 2) && (config[0] & 0x18) == 0x18 &&
         (config[1] & 0x18) == 0x10;
}
FlexReading readFlex(int pin) {
  analogRead(pin); // Discard the reading after changing ADC channel.
  delayMicroseconds(200);
  uint32_t total = 0;
  FlexReading result = {0, 4095, 0};
  for (int i = 0; i < 8; ++i) {
    uint16_t value = analogRead(pin);
    total += value;
    if (value < result.low) result.low = value;
    if (value > result.high) result.high = value;
  }
  result.mean = total / 8;
  return result;
}
void sensorTask(void *) {
  bool configured = initialiseIMU();
  uint32_t lastInitialise = millis(), seq = 0, errors = 0;
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    Sample s = {};
    s.seq = ++seq;
    s.us = esp_timer_get_time();
    TrialState snapshot;
    portENTER_CRITICAL(&stateMux);
    snapshot = state;
    portEXIT_CRITICAL(&stateMux);
    memcpy(s.session, snapshot.session, sizeof(s.session));
    // Labels come from the ESP acquisition time, not MQTT arrival time.
    if (snapshot.trial && s.us >= snapshot.startUs && s.us < snapshot.endUs) {
      s.trial = snapshot.trial;
      s.elapsedMs = (s.us - snapshot.startUs) / 1000;
    }
    s.thumb = readFlex(THUMB_PIN);
    s.index = readFlex(INDEX_PIN);
    s.middle = readFlex(MIDDLE_PIN);
    if (!configured && millis() - lastInitialise >= 2000) {
      lastInitialise = millis(); configured = initialiseIMU();
    }
    uint8_t bytes[14];
    s.imuOK = configured && readRegisters(0x3B, bytes, sizeof(bytes));
    if (s.imuOK) {
      for (int i = 0; i < 7; ++i)
        s.raw[i] = (int16_t)((uint16_t(bytes[2*i]) << 8) | bytes[2*i+1]);
    } else { ++errors; configured = false; }
    s.imuErrors = errors;
    s.queueDropped = queueDropped;
    if (xQueueSend(samples, &s, 0) != pdTRUE) {
      Sample old;
      if (xQueueReceive(samples, &old, 0) == pdTRUE) ++queueDropped;
      s.queueDropped = queueDropped;
      xQueueSend(samples, &s, 0);
    }
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(20)); // 50 Hz
  }
}
void sendAck(const TrialState &t, bool accepted) {
  char payload[220];
  snprintf(payload, sizeof(payload),
    "{\"boot\":\"%s\",\"session\":\"%s\",\"trial\":%u,\"accepted\":%s,\"start_us\":%llu,\"end_us\":%llu}",
    bootID, t.session, t.trial, accepted ? "true" : "false",
    (unsigned long long)t.startUs, (unsigned long long)t.endUs);
  mqtt.publish(ACK_TOPIC, payload, false);
}
void onCommand(char *, byte *payload, unsigned int length) {
  if (length == 0 || length >= 100) return;
  char text[100], session[17], extra;
  memcpy(text, payload, length); text[length] = '\0';
  unsigned int trial, duration;
  if (sscanf(text, "GO %16s %u %u %c", session, &trial, &duration, &extra) == 3 &&
      strlen(session) == 16 && trial >= 1 && trial <= 999 &&
      duration >= 1000 && duration <= 30000) {
    for (char *p = session; *p; ++p) if (!isxdigit((unsigned char)*p)) return;
    uint64_t now = esp_timer_get_time();
    TrialState t;
    bool accepted;
    portENTER_CRITICAL(&stateMux);
    // Repeated GO messages acknowledge the original trial; never restart it.
    if (!strcmp(session, state.session) && trial == state.trial) accepted = true;
    else if (now < state.endUs) accepted = false;
    else {
      strcpy(state.session, session); state.trial = trial;
      state.startUs = now; state.endUs = now + uint64_t(duration)*1000;
      accepted = true;
    }
    t = state;
    portEXIT_CRITICAL(&stateMux);
    sendAck(t, accepted);
  } else if (sscanf(text, "STOP %16s %c", session, &extra) == 1) {
    portENTER_CRITICAL(&stateMux);
    if (!strcmp(session, state.session)) state.endUs = esp_timer_get_time();
    portEXIT_CRITICAL(&stateMux);
  }
}
bool publishSample(const Sample &s) {
  char payload[850];
  // Preserve signed raw IMU counts as well as physical units.
  // Failed IMU readings are null, never plausible-looking zero vectors.
  char imu[450];
  if (s.imuOK) {
    snprintf(imu, sizeof(imu),
      "\"imu_ok\":true,\"raw_ax\":%d,\"raw_ay\":%d,\"raw_az\":%d,\"raw_gx\":%d,\"raw_gy\":%d,\"raw_gz\":%d,"
      "\"ax\":%.5f,\"ay\":%.5f,\"az\":%.5f,\"gx\":%.6f,\"gy\":%.6f,\"gz\":%.6f,\"temp_c\":%.3f",
      s.raw[0],s.raw[1],s.raw[2],s.raw[4],s.raw[5],s.raw[6],
      s.raw[0]*9.80665/4096.0,s.raw[1]*9.80665/4096.0,s.raw[2]*9.80665/4096.0,
      s.raw[4]*0.01745329252/16.4,s.raw[5]*0.01745329252/16.4,s.raw[6]*0.01745329252/16.4,
      s.raw[3]/340.0+36.53);
  } else strcpy(imu, "\"imu_ok\":false,\"ax\":null,\"ay\":null,\"az\":null,\"gx\":null,\"gy\":null,\"gz\":null,\"temp_c\":null");
  int n = snprintf(payload,sizeof(payload),
    "{\"version\":2,\"accel_range_g\":8,\"gyro_range_deg_s\":2000,\"boot\":\"%s\",\"session\":\"%s\",\"trial\":%u,\"seq\":%lu,\"timestamp_us\":%llu,\"elapsed_ms\":%lu,"
    "\"thumb\":%u,\"index\":%u,\"middle\":%u,\"thumb_min\":%u,\"thumb_max\":%u,\"index_min\":%u,\"index_max\":%u,\"middle_min\":%u,\"middle_max\":%u,"
    "%s,\"imu_errors\":%lu,\"queue_dropped\":%lu,\"rssi_dbm\":%d}",
    bootID,s.session,s.trial,(unsigned long)s.seq,(unsigned long long)s.us,(unsigned long)s.elapsedMs,
    s.thumb.mean,s.index.mean,s.middle.mean,s.thumb.low,s.thumb.high,s.index.low,s.index.high,s.middle.low,s.middle.high,
    imu,(unsigned long)s.imuErrors,(unsigned long)s.queueDropped,WiFi.RSSI());
  return n>0 && n<(int)sizeof(payload) && mqtt.publish(DATA_TOPIC,payload,false);
}
void networkTask(void *) {
  WiFi.persistent(false); WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true);
  WiFi.setSleep(false); WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  mqtt.setCallback(onCommand); mqtt.setKeepAlive(5); mqtt.setSocketTimeout(1);
  if (!mqtt.setBufferSize(1024)) { Serial.println("MQTT buffer allocation failed"); vTaskDelete(nullptr); }
  uint32_t lastAttempt=millis()-5000, wifiAttempt=millis(), lastBlink=0;
  bool led=false;
  char id[55], offline[120], online[200];
  snprintf(id,sizeof(id),"glove-test-%08lx-%s",(unsigned long)ESP.getEfuseMac(),bootID);
  snprintf(offline,sizeof(offline),"{\"state\":\"OFFLINE\",\"boot\":\"%s\"}",bootID);
  snprintf(online,sizeof(online),"{\"state\":\"ONLINE\",\"boot\":\"%s\",\"firmware\":\"glove_quick_range_retest_v2\",\"sample_hz\":50,\"accel_range_g\":8,\"gyro_range_deg_s\":2000}",bootID);
  for (;;) {
    uint32_t now=millis();
    if (WiFi.status()!=WL_CONNECTED) {
      transport.stop();
      if (now-wifiAttempt>=20000) { WiFi.disconnect(false); WiFi.begin(WIFI_SSID,WIFI_PASSWORD); wifiAttempt=now; }
    } else if (!mqtt.connected() && now-lastAttempt>=3000) {
      lastAttempt=now; transport.stop();
      if (mqtt.connect(id,STATUS_TOPIC,1,true,offline)) {
        if (mqtt.subscribe(CONTROL_TOPIC,1) && mqtt.publish(STATUS_TOPIC,online,true)) xQueueReset(samples);
        else transport.stop();
      }
    }
    if (WiFi.status()==WL_CONNECTED && mqtt.connected()) {
      if (!mqtt.loop()) transport.stop();
      else {
        Sample s;
        if (xQueueReceive(samples,&s,0)==pdTRUE && !publishSample(s)) transport.stop();
        digitalWrite(LED_BUILTIN,HIGH); led=true;
      }
    } else {
      uint32_t period=WiFi.status()==WL_CONNECTED ? 1000 : 250;
      if (now-lastBlink>=period) { lastBlink=now; led=!led; digitalWrite(LED_BUILTIN,led); }
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}
void setup() {
  Serial.begin(115200); pinMode(LED_BUILTIN,OUTPUT); digitalWrite(LED_BUILTIN,LOW);
  snprintf(bootID,sizeof(bootID),"%08lx",(unsigned long)esp_random());
  Wire.begin(21,22); Wire.setClock(100000); Wire.setTimeOut(20);
  analogReadResolution(12);
  for (int pin : {THUMB_PIN,INDEX_PIN,MIDDLE_PIN}) {
    pinMode(pin,INPUT); analogSetPinAttenuation(pin,ADC_11db);
  }
  samples=xQueueCreate(100,sizeof(Sample));
  if (!samples) { Serial.println("Sample queue allocation failed"); return; }
  if (xTaskCreatePinnedToCore(sensorTask,"sensors",4096,nullptr,2,nullptr,1)!=pdPASS ||
      xTaskCreatePinnedToCore(networkTask,"network",8192,nullptr,1,nullptr,0)!=pdPASS) {
    Serial.println("Task creation failed");
  }
}
void loop() { delay(1000); }
