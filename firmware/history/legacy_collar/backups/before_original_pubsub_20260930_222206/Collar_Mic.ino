// Demo firmware: records continuously and publishes each completed four-second WAV.
// No wake-word model, command recognition, or loudness gate.
#include <Arduino.h>
#include "ESP_I2S.h"
#include <WiFi.h>
#include <CollarMqtt.h>

const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";
const char MQTT_BROKER_IP[] = "172.20.10.2";
const uint16_t MQTT_BROKER_PORT = 1883;
const uint32_t MQTT_RETRY_MS = 5000;
const char CONNECTION_TOPIC[] = "status/collar/connection";
const char CONNECTION_ONLINE_PAYLOAD[] = "{\"type\":\"connection_status\",\"state\":\"ONLINE\"}";
const char CONNECTION_OFFLINE_PAYLOAD[] = "{\"type\":\"connection_status\",\"state\":\"OFFLINE\"}";

// INMP441: VDD -> 3V3, GND and L/R -> GND. Pin numbers are GPIO numbers.
const int MIC_BCLK = 14, MIC_WS = 17, MIC_SD = 16;
const uint32_t SAMPLE_RATE = 16000;
const uint32_t FRAME_SAMPLES = 320; // 20 ms
const uint32_t BLOCK_SAMPLES = 16000; // one second of signed 16-bit PCM
const uint32_t BLOCK_BYTES = BLOCK_SAMPLES * sizeof(int16_t);
const uint8_t BLOCK_COUNT = 5; // four seconds plus one second of upload headroom
const uint8_t CLIP_BLOCKS = 4;
const uint8_t NO_BLOCK = 255;

I2SClass microphone;
WiFiClient wifiClient;
CollarMqtt mqtt(wifiClient);
int16_t *audioBlocks[BLOCK_COUNT] = {};
QueueHandle_t freeBlocks, readyClips;
uint32_t sessionId;

struct AudioClip {
  uint8_t blocks[CLIP_BLOCKS];
  uint32_t id;
  uint32_t finishedMs;
};

// Explicit declarations keep Arduino's automatic prototype generation unambiguous.
void releaseClip(AudioClip &clip);
void makeWavHeader(uint8_t *header);
void microphoneTask(void *parameter);
bool publishWav(AudioClip &clip);
void networkTask(void *parameter);

void releaseClip(AudioClip &clip) {
  for (uint8_t &block : clip.blocks) {
    if (block != NO_BLOCK) {
      xQueueSend(freeBlocks, &block, 0);
      block = NO_BLOCK;
    }
  }
}

void makeWavHeader(uint8_t *header) {
  const uint32_t dataBytes = CLIP_BLOCKS * BLOCK_BYTES;
  memset(header, 0, 44);
  memcpy(header, "RIFF", 4);
  uint32_t riffBytes = dataBytes + 36;
  memcpy(header + 4, &riffBytes, 4);
  memcpy(header + 8, "WAVEfmt ", 8);
  uint32_t fmtBytes = 16, rate = SAMPLE_RATE, byteRate = SAMPLE_RATE * 2;
  uint16_t format = 1, channels = 1, alignment = 2, bits = 16;
  // ESP32 is little-endian, as required by PCM WAV.
  memcpy(header + 16, &fmtBytes, 4);
  memcpy(header + 20, &format, 2);
  memcpy(header + 22, &channels, 2);
  memcpy(header + 24, &rate, 4);
  memcpy(header + 28, &byteRate, 4);
  memcpy(header + 32, &alignment, 2);
  memcpy(header + 34, &bits, 2);
  memcpy(header + 36, "data", 4);
  memcpy(header + 40, &dataBytes, 4);
}

void microphoneTask(void *parameter) {
  int32_t raw[FRAME_SAMPLES];
  AudioClip clip = {{NO_BLOCK, NO_BLOCK, NO_BLOCK, NO_BLOCK}, 0, 0};
  uint32_t frames = 0, nextId = 0, dropped = 0, readGaps = 0;
  uint32_t peak = 0;
  bool discard = false;
  for (;;) {
    size_t bytes = microphone.readBytes(reinterpret_cast<char *>(raw), sizeof(raw));
    if (bytes != sizeof(raw)) {
      // Never publish a WAV containing missing/uninitialized samples.
      releaseClip(clip);
      frames = 0; peak = 0; discard = false;
      Serial.printf("# Audio read gap: %lu; restarting four-second recording\n",
                    (unsigned long)++readGaps);
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    const uint32_t samplesSoFar = frames * FRAME_SAMPLES;
    const uint8_t blockIndex = samplesSoFar / BLOCK_SAMPLES;
    const uint32_t offset = samplesSoFar % BLOCK_SAMPLES;
    if (!discard && offset == 0 &&
        xQueueReceive(freeBlocks, &clip.blocks[blockIndex], 0) != pdTRUE) {
      // The network is too slow. Keep reading the mic, but drop this entire window.
      releaseClip(clip);
      discard = true;
    }
    if (!discard) {
      int16_t *destination = audioBlocks[clip.blocks[blockIndex]] + offset;
      for (uint32_t i = 0; i < FRAME_SAMPLES; ++i) {
        // Same gain as the previously tested recorder and collar firmware.
        int32_t value = (raw[i] >> 16) * 4;
        destination[i] = constrain(value, -32768, 32767);
        peak = max(peak, uint32_t(abs(int32_t(destination[i]))));
      }
    }
    if (++frames == SAMPLE_RATE * CLIP_BLOCKS / FRAME_SAMPLES) {
      clip.id = ++nextId;
      if (clip.id == 0) clip.id = ++nextId;
      clip.finishedMs = millis();
      if (discard || xQueueSend(readyClips, &clip, 0) != pdTRUE) {
        releaseClip(clip);
        Serial.printf("# Recording dropped: network/buffer busy; total=%lu\n",
                      (unsigned long)++dropped);
      } else {
        // Ownership has moved to the network task; it releases each block after sending.
        for (uint8_t &block : clip.blocks) block = NO_BLOCK;
        Serial.printf("# Recorded 4 s: clip=%lu peak=%lu\n",
                      (unsigned long)clip.id, (unsigned long)peak);
      }
      frames = 0; peak = 0; discard = false;
    }
  }
}

bool publishWav(AudioClip &clip) {
  char topic[100];
  snprintf(topic, sizeof(topic), "sensor/collar/voice/wav/%08lx/%lu",
           (unsigned long)sessionId, (unsigned long)clip.id);
  uint8_t header[44];
  makeWavHeader(header);
  const uint32_t started = millis();
  // These writes are parts of ONE MQTT message, not separate audio messages.
  if (!mqtt.beginPublish(topic, sizeof(header) + CLIP_BLOCKS * BLOCK_BYTES, false)) return false;
  if (mqtt.write(header, sizeof(header)) != sizeof(header)) return false;
  for (uint8_t i = 0; i < CLIP_BLOCKS; ++i) {
    const uint8_t *data = reinterpret_cast<const uint8_t *>(audioBlocks[clip.blocks[i]]);
    for (uint32_t offset = 0; offset < BLOCK_BYTES; offset += FRAME_SAMPLES * 2) {
      if (WiFi.status() != WL_CONNECTED || millis() - started > 3000) return false;
      if (mqtt.write(data + offset, FRAME_SAMPLES * 2) != FRAME_SAMPLES * 2) return false;
      if ((offset / (FRAME_SAMPLES * 2)) % 8 == 7) vTaskDelay(pdMS_TO_TICKS(1));
    }
    // Free this second of audio immediately so the mic can keep recording.
    xQueueSend(freeBlocks, &clip.blocks[i], 0);
    clip.blocks[i] = NO_BLOCK;
  }
  if (!mqtt.endPublish()) return false;
  Serial.printf("# WAV sent: %s bytes=128044 upload_ms=%lu\n",
                topic, (unsigned long)(millis() - started));
  return true;
}

void networkTask(void *parameter) {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  wifiClient.setTimeout(1000);
  mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(1);
  if (!mqtt.setBufferSize(1024)) {
    Serial.println("# ERROR: MQTT memory allocation failed; reset board");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t wifiStarted = millis(), lastStatus = 0;
  uint32_t lastMqttAttempt = millis() - MQTT_RETRY_MS;
  bool previouslyConnected = false;
  for (;;) {
    const uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
      wifiClient.stop();
      previouslyConnected = false;
      if (now - lastStatus >= 5000) {
        Serial.printf("# Wi-Fi waiting, status=%d\n", int(WiFi.status()));
        lastStatus = now;
      }
      if (now - wifiStarted >= 20000) {
        WiFi.disconnect(false);
        vTaskDelay(pdMS_TO_TICKS(250));
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        wifiStarted = millis();
      }
    } else {
      if (!previouslyConnected) {
        previouslyConnected = true;
        wifiClient.stop();
        Serial.print("# Wi-Fi connected, IP="); Serial.println(WiFi.localIP());
        lastMqttAttempt = now - MQTT_RETRY_MS;
      }
      if (!mqtt.connected() && now - lastMqttAttempt >= MQTT_RETRY_MS) {
        lastMqttAttempt = now;
        char clientId[40];
        snprintf(clientId, sizeof(clientId), "collar-%012llx", (unsigned long long)ESP.getEfuseMac());
        Serial.print("# MQTT connecting to "); Serial.println(MQTT_BROKER_IP);
        if (mqtt.connect(clientId, CONNECTION_TOPIC, 1, true, CONNECTION_OFFLINE_PAYLOAD) &&
            mqtt.publish(CONNECTION_TOPIC, CONNECTION_ONLINE_PAYLOAD, true)) {
          Serial.printf("# MQTT connected; free_heap=%lu\n", (unsigned long)ESP.getFreeHeap());
        } else {
          Serial.printf("# MQTT failed, state=%d\n", mqtt.state());
          wifiClient.stop();
        }
      }
      if (mqtt.connected() && !mqtt.loop()) wifiClient.stop();
    }
    AudioClip clip;
    if (xQueueReceive(readyClips, &clip, 0) == pdTRUE) {
      if (WiFi.status() == WL_CONNECTED && mqtt.connected() && millis() - clip.finishedMs < 1000) {
        if (!publishWav(clip)) {
          // Close a partial MQTT message before any retry or other publish.
          wifiClient.stop();
          Serial.println("# WAV send failed; clip dropped, no replay");
        }
      } else {
        Serial.println("# WAV dropped: offline or stale; no replay");
      }
      releaseClip(clip);
    }
    digitalWrite(LED_BUILTIN, mqtt.connected() ? HIGH : LOW);
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  freeBlocks = xQueueCreate(BLOCK_COUNT, sizeof(uint8_t));
  readyClips = xQueueCreate(1, sizeof(AudioClip));
  bool allocated = freeBlocks && readyClips;
  for (uint8_t i = 0; i < BLOCK_COUNT && allocated; ++i) {
    audioBlocks[i] = static_cast<int16_t *>(malloc(BLOCK_BYTES));
    allocated = audioBlocks[i] != nullptr;
    if (allocated) xQueueSend(freeBlocks, &i, 0);
  }
  if (!allocated) {
    Serial.println("# ERROR: audio buffer allocation failed; reset board");
    while (true) delay(1000);
  }
  sessionId = esp_random();
  microphone.setPins(MIC_BCLK, MIC_WS, -1, MIC_SD);
  if (!microphone.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                        I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("# ERROR: microphone initialization failed; check wiring");
    while (true) delay(1000);
  }
  Serial.println("# Collar demo: continuous four-second WAVs; NO wake-word detection");
  if (xTaskCreatePinnedToCore(microphoneTask, "collarAudio", 4096, nullptr, 2, nullptr, 1) != pdPASS ||
      xTaskCreatePinnedToCore(networkTask, "collarNetwork", 6144, nullptr, 1, nullptr, 0) != pdPASS) {
    Serial.println("# ERROR: task allocation failed; reset board");
    while (true) delay(1000);
  }
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
