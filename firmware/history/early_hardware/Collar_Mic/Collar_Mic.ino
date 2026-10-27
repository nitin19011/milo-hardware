#include <Arduino.h>
#include "ESP_I2S.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <atomic>

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
const uint32_t BLOCK_SAMPLES = 3200; // 200 ms of signed 16-bit PCM
const uint32_t BLOCK_BYTES = BLOCK_SAMPLES * sizeof(int16_t);
const uint8_t CLIP_BLOCKS = 20; // Still exactly four seconds, not twenty seconds.
const uint8_t BLOCK_COUNT = CLIP_BLOCKS + 1; // 134,400 bytes; saves 25,600 bytes for Wi-Fi.
const uint8_t NO_BLOCK = 255;
static_assert(BLOCK_SAMPLES % FRAME_SAMPLES == 0, "Audio frames must fit whole blocks");
static_assert(BLOCK_SAMPLES * CLIP_BLOCKS == SAMPLE_RATE * 4, "WAV must remain four seconds");

I2SClass microphone;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
int16_t *audioBlocks[BLOCK_COUNT] = {};
QueueHandle_t freeBlocks, readyClips;
uint32_t sessionId;
std::atomic<bool> audioEnabled{false}; // Only collect clips after ONLINE was published.

struct AudioClip {
  uint8_t blocks[CLIP_BLOCKS];
  uint32_t id;
  uint32_t finishedMs;
};

// Explicit declarations keep Arduino's automatic prototype generation unambiguous.
void releaseClip(AudioClip &clip);
void makeWavHeader(uint8_t *header);
void microphoneTask(void *parameter);
bool beginWavPublish(const char *topic, uint32_t wavBytes);
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
  AudioClip clip{};
  for (uint8_t &block : clip.blocks) block = NO_BLOCK;
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
    if (!audioEnabled.load()) {
      // Drain I2S continuously, but do not fill audio buffers while reconnecting.
      releaseClip(clip);
      frames = 0; peak = 0; discard = false;
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
    if (++frames == BLOCK_SAMPLES * CLIP_BLOCKS / FRAME_SAMPLES) {
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

// PubSubClient 2.8's beginPublish uses a 16-bit internal length. Build only
// this large QoS-0, non-retained PUBLISH header here; the library stays unchanged.
// networkTask exclusively owns MQTT. Do not call loop/publish during this send;
// the caller MUST close the connection if any header or payload write fails.
bool beginWavPublish(const char *topic, uint32_t wavBytes) {
  if (!topic || !mqtt.connected() || wavBytes != 44 + CLIP_BLOCKS * BLOCK_BYTES) return false;
  const size_t topicLength = strlen(topic);
  if (topicLength == 0 || topicLength >= 100) return false;
  uint32_t remaining = 2 + uint32_t(topicLength) + wavBytes;
  uint8_t header[7]; // type + up to four Remaining Length bytes + two topic-length bytes
  size_t length = 0;
  header[length++] = 0x30; // MQTT PUBLISH, QoS 0, not retained
  do {
    uint8_t digit = remaining & 0x7f;
    remaining >>= 7;
    if (remaining) digit |= 0x80;
    header[length++] = digit;
  } while (remaining);
  header[length++] = uint8_t(topicLength >> 8);
  header[length++] = uint8_t(topicLength);
  // Public write() sends raw bytes and updates PubSubClient's keep-alive activity.
  return mqtt.write(header, length) == length &&
         mqtt.write(reinterpret_cast<const uint8_t *>(topic), topicLength) == topicLength;
}

bool publishWav(AudioClip &clip) {
  char topic[100];
  snprintf(topic, sizeof(topic), "sensor/collar/voice/wav/%08lx/%lu",
           (unsigned long)sessionId, (unsigned long)clip.id);
  uint8_t header[44];
  makeWavHeader(header);
  const uint32_t started = millis();
  // These writes are parts of ONE MQTT message, not separate audio messages.
  if (!beginWavPublish(topic, sizeof(header) + CLIP_BLOCKS * BLOCK_BYTES)) return false;
  if (mqtt.write(header, sizeof(header)) != sizeof(header)) return false;
  for (uint8_t i = 0; i < CLIP_BLOCKS; ++i) {
    const uint8_t *data = reinterpret_cast<const uint8_t *>(audioBlocks[clip.blocks[i]]);
    for (uint32_t offset = 0; offset < BLOCK_BYTES; offset += FRAME_SAMPLES * 2) {
      if (WiFi.status() != WL_CONNECTED || millis() - started > 3000) return false;
      if (mqtt.write(data + offset, FRAME_SAMPLES * 2) != FRAME_SAMPLES * 2) return false;
      if ((offset / (FRAME_SAMPLES * 2)) % 8 == 7) vTaskDelay(pdMS_TO_TICKS(1));
    }
    // Free each 200 ms block promptly so the mic can keep recording with less spare RAM.
    xQueueSend(freeBlocks, &clip.blocks[i], 0);
    clip.blocks[i] = NO_BLOCK;
  }
  // All declared bytes have been written. QoS 0 has no broker acknowledgement.
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
  mqtt.setSocketTimeout(3); // Allow a hotspot time to return MQTT CONNACK.
  if (!mqtt.setBufferSize(1024)) {
    Serial.println("# ERROR: MQTT memory allocation failed; reset board");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t wifiStarted = millis(), lastStatus = 0;
  uint32_t lastMqttAttempt = millis() - MQTT_RETRY_MS;
  uint32_t lastLedToggle = 0;
  bool ledState = false;
  bool previouslyConnected = false;
  for (;;) {
    const uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
      audioEnabled.store(false);
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
        audioEnabled.store(false);
        wifiClient.stop();
        Serial.print("# Wi-Fi connected, IP="); Serial.println(WiFi.localIP());
        lastMqttAttempt = now - MQTT_RETRY_MS;
      }
      if (!mqtt.connected()) audioEnabled.store(false);
      if (!mqtt.connected() && now - lastMqttAttempt >= MQTT_RETRY_MS) {
        // Release queued offline audio before any potentially blocking connection call.
        AudioClip stale;
        while (xQueueReceive(readyClips, &stale, 0) == pdTRUE) releaseClip(stale);
        wifiClient.stop();
        char clientId[40];
        snprintf(clientId, sizeof(clientId), "collar-%012llx", (unsigned long long)ESP.getEfuseMac());
        Serial.print("# MQTT connecting to "); Serial.println(MQTT_BROKER_IP);
        // Separate TCP, MQTT handshake, and status publication failures.
        if (!wifiClient.connect(MQTT_BROKER_IP, MQTT_BROKER_PORT, 1000)) {
          Serial.println("# TCP connection failed (before MQTT handshake)");
        } else {
          wifiClient.setNoDelay(true);
          if (!mqtt.connect(clientId, CONNECTION_TOPIC, 1, true, CONNECTION_OFFLINE_PAYLOAD)) {
            Serial.printf("# MQTT handshake failed, state=%d\n", mqtt.state());
          } else if (!mqtt.publish(CONNECTION_TOPIC, CONNECTION_ONLINE_PAYLOAD, true)) {
            Serial.printf("# MQTT handshake succeeded, but ONLINE publish failed; state=%d\n", mqtt.state());
          } else {
            audioEnabled.store(true);
            Serial.println("# MQTT connected; ONLINE sent; starting four-second recordings");
          }
        }
        if (!audioEnabled.load()) {
          wifiClient.stop();
        }
        lastMqttAttempt = millis(); // Wait five seconds AFTER a failed attempt finishes.
      }
      if (mqtt.connected() && !mqtt.loop()) {
        audioEnabled.store(false);
        Serial.printf("# MQTT connection lost, state=%d\n", mqtt.state());
        wifiClient.stop();
        lastMqttAttempt = millis();
      }
    }
    AudioClip clip;
    if (xQueueReceive(readyClips, &clip, 0) == pdTRUE) {
      if (WiFi.status() == WL_CONNECTED && mqtt.connected() && millis() - clip.finishedMs < 1000) {
        if (!publishWav(clip)) {
          // Close a partial MQTT message before any retry or other publish.
          audioEnabled.store(false);
          wifiClient.stop();
          lastMqttAttempt = millis();
          Serial.println("# WAV send failed; clip dropped, no replay");
        }
      } else {
        Serial.println("# WAV dropped: offline or stale; no replay");
      }
      releaseClip(clip);
    }
    // Same status patterns as the glove. No blocking delays for blinking.
    const uint32_t ledNow = millis();
    const bool wifiConnected = WiFi.status() == WL_CONNECTED;
    if (wifiConnected && mqtt.connected()) {
      ledState = true; // Solid: Wi-Fi and MQTT connected.
      lastLedToggle = ledNow;
    } else {
      // Fast: Wi-Fi disconnected. Slow: Wi-Fi works, MQTT disconnected.
      const uint32_t blinkInterval = wifiConnected ? 1000 : 250;
      if (ledNow - lastLedToggle >= blinkInterval) {
        lastLedToggle = ledNow;
        ledState = !ledState;
      }
    }
    digitalWrite(LED_BUILTIN, ledState ? HIGH : LOW);
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
