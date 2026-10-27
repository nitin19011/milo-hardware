#include <ArduinoJson.h>
#include <ArduinoJson.hpp>

// Glove-only LOCAL candidate model prototype. No MQTT, microphone or cue buzzes.
// USB: 230400 baud. Optional Wi-Fi UDP is configured by the desktop UI over USB.
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <esp_system.h>
#include "CandidateFeatures.h"
#include "CandidateModel.h"

const int FLEX_PINS[3] = {35, 34, 39};
const int BEND[3] = {1696, 1920, 3520};
const int RELEASE[3] = {1583, 1762, 3487};
const uint8_t MPU = 0x68;
struct Row {
  uint64_t us;
  uint32_t seq, imuErrors, queueDrops;
  float axes[6];
  uint16_t raw[3];
  uint8_t states[3], imuOk, clipped, rails;
  float score;
  uint32_t proposalId, proposalSeq, inferenceUs;
  uint64_t proposalUs;
  uint8_t modelReady;
};
// Sensor-task-owned 3-second history, including the 0.8-second model window.
static Row history[150];
static uint16_t historyPos=0,historyCount=0,goodCount=0;
static uint32_t proposalId=0,proposalSeq=0,inferenceUs=0;
static uint64_t proposalUs=0,lastSampleUs=0;
static float lastScore=0;
static bool modelReady=false;
static void observeCandidate(Row &r) {
  history[historyPos]=r;historyPos=(historyPos+1)%150;
  if(historyCount<150)historyCount++;
  bool healthy=r.imuOk&&!r.clipped&&!r.rails;
  if(!healthy||(lastSampleUs&&r.us-lastSampleUs>40000)){goodCount=0;modelReady=false;lastScore=0;}
  if(healthy&&goodCount<150)goodCount++;
  lastSampleUs=r.us;
  if(goodCount>=40&&r.seq%5==0) {
    int64_t begin=esp_timer_get_time();float window[40][12],x[45];
    for(int i=0;i<40;i++) {
      const Row &q=history[(historyPos+150-40+i)%150];
      for(int c=0;c<6;c++)window[i][c]=q.axes[c];
      for(int c=0;c<3;c++){window[i][6+c]=q.states[c];window[i][9+c]=q.raw[c];}
    }
    miloFeatures(window,x);lastScore=miloPredict(x);modelReady=true;
    inferenceUs=uint32_t(esp_timer_get_time()-begin);
    // Repeated proposals allow a new action during sustained motion. No straighten-to-rearm gate.
    // The first proposal waits for 1 second of valid prehistory, once at startup/fault recovery.
    if(goodCount>=50&&lastScore>=MILO_TRIGGER_THRESHOLD&&(!proposalId||r.us-proposalUs>=1000000)) {
      proposalId++;proposalUs=r.us;proposalSeq=r.seq;
    }
  }
  r.score=lastScore;r.proposalId=proposalId;r.proposalUs=proposalUs;r.proposalSeq=proposalSeq;
  r.modelReady=modelReady;r.inferenceUs=inferenceUs;
}
QueueHandle_t rows;
uint32_t queueDrops = 0;
char bootId[17];
String wifiSsid, wifiPass, targetHost, command;
uint16_t targetPort = 25400;
IPAddress destination;
WiFiUDP udp;
bool udpStarted = false;
uint32_t lastConnect = 0;

bool readReg(uint8_t reg, uint8_t *out, uint8_t n) {
  Wire.beginTransmission(MPU); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU, n) != n) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint8_t i = 0; i < n; ++i) out[i] = Wire.read();
  return true;
}
bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU); Wire.write(reg); Wire.write(value);
  return Wire.endTransmission() == 0;
}
bool setupImu() {
  uint8_t who = 0, ranges[2];
  return readReg(0x75, &who, 1) && who == 0x68 &&
    writeReg(0x6B, 1) && writeReg(0x6C, 0) && writeReg(0x1A, 4) &&
    writeReg(0x19, 4) && writeReg(0x1B, 0x18) && writeReg(0x1C, 0x18) &&
    readReg(0x1B, ranges, 2) && (ranges[0] & 0x18) == 0x18 && (ranges[1] & 0x18) == 0x18;
}
int readFlex(int pin) {
  analogRead(pin); delayMicroseconds(200);
  uint32_t total = 0;
  for (int i = 0; i < 8; ++i) total += analogRead(pin);
  return total / 8;
}
void sampleTask(void *) {
  bool ready = setupImu(), states[3] = {};
  uint32_t seq = 0, errors = 0, lastRetry = millis();
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(20));
    Row r = {}; r.us = esp_timer_get_time(); r.seq = seq++;
    if (!ready && millis() - lastRetry >= 2000) { lastRetry = millis(); ready = setupImu(); }
    uint8_t data[14];
    r.imuOk = ready && readReg(0x3B, data, sizeof(data));
    if (!r.imuOk) { ++errors; ready = false; }
    else for (int i = 0; i < 6; ++i) {
      int source = i < 3 ? i : i + 1;
      int16_t raw = int16_t((uint16_t(data[source * 2]) << 8) | data[source * 2 + 1]);
      if (abs(int(raw)) >= 32700) r.clipped = 1;
      r.axes[i] = i < 3 ? raw * 9.80665f / 2048.0f : raw * 0.01745329252f / 16.4f;
    }
    for (int i = 0; i < 3; ++i) {
      r.raw[i] = readFlex(FLEX_PINS[i]);
      if (r.raw[i] <= 20 || r.raw[i] >= 4075) r.rails |= 1 << i;
      else states[i] = states[i] ? r.raw[i] > RELEASE[i] : r.raw[i] >= BEND[i];
      r.states[i] = states[i];
    }
    r.imuErrors = errors; r.queueDrops = queueDrops;
    observeCandidate(r);
    if (xQueueSend(rows, &r, 0) != pdTRUE) {
      Row discarded;
      if (xQueueReceive(rows, &discarded, 0) == pdTRUE) ++queueDrops;
      r.queueDrops = queueDrops;
      xQueueSend(rows, &r, 0);
    }
  }
}
void loadWifi() {
  Preferences p; p.begin("milo-candidate", true);
  wifiSsid = p.getString("ssid", ""); wifiPass = p.getString("pass", "");
  targetHost = p.getString("host", ""); targetPort = p.getUShort("port", 25400);
  p.end(); destination.fromString(targetHost);
}
void applyCommand(const String &line) {
  JsonDocument d;
  if (deserializeJson(d, line) || strcmp(d["cmd"] | "", "wifi")) return;
  String ssid = d["ssid"] | "", pass = d["password"] | "", host = d["host"] | "";
  int port = d["port"] | 25400; IPAddress ip;
  if (!ssid.length() || ssid.length() > 32 || pass.length() > 63 || !ip.fromString(host) || port < 1024 || port > 65535) {
    Serial.println("#CONFIG_ERROR invalid settings"); return;
  }
  Preferences p; p.begin("milo-candidate", false);
  p.putString("ssid", ssid); p.putString("pass", pass); p.putString("host", host); p.putUShort("port", port); p.end();
  wifiSsid = ssid; wifiPass = pass; targetHost = host; targetPort = port; destination = ip;
  udp.stop(); udpStarted = false; WiFi.disconnect(); lastConnect = 0;
  Serial.println("#CONFIG_OK"); // Never echo credentials.
}
void transportTask(void *) {
  uint32_t lastIp = 0;
  for (;;) {
    while (Serial.available()) {
      char c = Serial.read();
      if (c == '\n') { applyCommand(command); command = ""; }
      else if (c != '\r') {
        command += c;
        if (command.length() > 1024) command = "";
      }
    }
    if (wifiSsid.length() && destination != IPAddress(0, 0, 0, 0)) {
      if (WiFi.status() != WL_CONNECTED) {
        if (udpStarted) { udp.stop(); udpStarted = false; }
        if (!lastConnect || millis() - lastConnect >= 10000) {
          lastConnect = millis(); WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
        }
      } else {
        if (!udpStarted) udpStarted = udp.begin(25401) == 1;
        uint32_t ip = uint32_t(WiFi.localIP());
        if (ip != lastIp) { lastIp = ip; Serial.printf("#WIFI_IP %s\n", WiFi.localIP().toString().c_str()); }
      }
    }
    Row r;
    if (xQueueReceive(rows, &r, pdMS_TO_TICKS(10)) != pdTRUE) continue;
    char packet[384];
    int n = snprintf(packet, sizeof(packet),
      "MILO2,%s,%lu,%llu,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%u,%u,%u,%u,%u,%u,%u,%u,%u,%lu,%lu,%.6f,%lu,%llu,%lu,%u,%lu\n",
      bootId, (unsigned long)r.seq, (unsigned long long)r.us,
      r.axes[0], r.axes[1], r.axes[2], r.axes[3], r.axes[4], r.axes[5],
      r.states[0], r.states[1], r.states[2], r.raw[0], r.raw[1], r.raw[2],
      r.imuOk, r.clipped, r.rails, (unsigned long)r.imuErrors, (unsigned long)r.queueDrops,
      r.score,(unsigned long)r.proposalId,(unsigned long long)r.proposalUs,(unsigned long)r.proposalSeq,r.modelReady,(unsigned long)r.inferenceUs);
    if (n <= 0 || n >= int(sizeof(packet))) continue;
    Serial.write((const uint8_t *)packet, n);
    if (udpStarted && WiFi.status() == WL_CONNECTED && udp.beginPacket(destination, targetPort)) {
      udp.write((const uint8_t *)packet, n); udp.endPacket();
    }
  }
}
void setup() {
  pinMode(25, OUTPUT); digitalWrite(25, LOW); // Motor remains off throughout collection.
  Serial.begin(230400);
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  analogReadResolution(12);
  for (int pin : FLEX_PINS) { pinMode(pin, INPUT); analogSetPinAttenuation(pin, ADC_11db); }
  Wire.begin(21, 22); Wire.setClock(100000); Wire.setTimeOut(15);
  WiFi.mode(WIFI_STA); WiFi.setSleep(false); loadWifi();
  rows = xQueueCreate(128, sizeof(Row));
  if (!rows) { Serial.println("#FATAL queue"); while (true) delay(1000); }
  if (xTaskCreatePinnedToCore(sampleTask, "sample50", 8192, nullptr, 2, nullptr, 1) != pdPASS ||
      xTaskCreatePinnedToCore(transportTask, "stream", 6144, nullptr, 1, nullptr, 0) != pdPASS) {
    Serial.println("#FATAL tasks"); while (true) delay(1000);
  }
  Serial.println("#READY MILO2 local_model_v1 threshold=0.1 50Hz calibration=nitin-20261023-usb-relaxed-fist-v3");
}
void loop() { vTaskDelay(pdMS_TO_TICKS(1000)); }
