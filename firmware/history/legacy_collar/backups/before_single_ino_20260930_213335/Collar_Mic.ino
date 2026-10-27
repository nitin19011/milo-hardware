#include <Arduino.h>
#include "ESP_I2S.h"
#include <WiFi.h>
#include "CollarMqtt.h"
#include <esp_timer.h>
#include "MiloCapture.h"

const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";
const char MQTT_BROKER_IP[] = "172.20.10.2";
const uint16_t MQTT_BROKER_PORT = 1883;
const uint32_t MQTT_RETRY_MS = 5000;
const char MIC_TOPIC[] = "sensor/collar/microphone";
const char CONNECTION_TOPIC[] = "status/collar/connection";
const char CONNECTION_ONLINE_PAYLOAD[] =
  "{\"schema_version\":1,\"type\":\"connection_status\",\"source_id\":\"collar\",\"state\":\"ONLINE\"}";
const char CONNECTION_OFFLINE_PAYLOAD[] =
  "{\"schema_version\":1,\"type\":\"connection_status\",\"source_id\":\"collar\",\"state\":\"OFFLINE\"}";

// INMP441 VDD->3V3; GND AND L/R->GND. These are GPIO numbers.
const int MIC_BCLK=14, MIC_WS=17, MIC_SD=16;
const uint32_t MIC_RATE=16000, MIC_PUBLISH_MS=200;
I2SClass microphone;
WiFiClient wifiClient;
CollarMqtt mqtt(wifiClient);
MiloCapture milo;
struct MicSample {
  uint32_t sequence;
  uint64_t timestampUs;
  float rms;
  uint32_t peak;
  bool valid;
  float wakeDistance;
  uint32_t abortedClips,readGaps,computeOverruns,busyFrames;
};
QueueHandle_t micQueue;
void forceMqttReconnect() {
  milo.setOnline(false);
  wifiClient.stop();
  digitalWrite(LED_BUILTIN,LOW);
}

// Audio gain MUST match Collar_Recorder. No Serial PCM in this operational sketch.
void microphoneTask(void *parameter) {
  int32_t raw[320];
  int16_t pcm[320];
  uint32_t seq=0,lastPublish=millis(),lastPrint=0;
  for (;;) {
    const size_t bytes=microphone.readBytes(reinterpret_cast<char *>(raw),sizeof(raw));
    if (bytes!=sizeof(raw)) {
      milo.gap();
      MicSample failed{}; failed.sequence=seq++;
      failed.timestampUs=esp_timer_get_time(); failed.wakeDistance=1e9f;
      failed.abortedClips=milo.abortedClips;failed.readGaps=milo.readGaps;
      failed.computeOverruns=milo.computeOverruns;failed.busyFrames=milo.busyFrames;
      xQueueOverwrite(micQueue,&failed);
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    double sum=0,squares=0; uint32_t peak=0;
    for (int i=0;i<320;++i) {
      const int32_t value=(raw[i]>>16)*4;
      pcm[i]=constrain(value,-32768,32767);
      sum+=pcm[i]; squares+=double(pcm[i])*pcm[i];
      peak=max(peak,uint32_t(abs(int32_t(pcm[i]))));
    }
    double mean=sum/320;
    double variance=squares/320-mean*mean;
    float rms=sqrt(variance>0?variance:0);
    milo.feed(pcm,rms);
    if (millis()-lastPublish>=MIC_PUBLISH_MS) {
      MicSample sample{};
      sample.sequence=seq++; sample.timestampUs=esp_timer_get_time();
      sample.rms=rms;sample.peak=peak;sample.valid=true;
      sample.wakeDistance=milo.bestSinceStatus;
      sample.abortedClips=milo.abortedClips;sample.readGaps=milo.readGaps;
      sample.computeOverruns=milo.computeOverruns;sample.busyFrames=milo.busyFrames;
      xQueueOverwrite(micQueue,&sample);
      milo.bestSinceStatus=1e9f;lastPublish=millis();
      if (millis()-lastPrint>=1000) {
        Serial.printf("# mic rms=%.1f peak=%lu model=%s aborted=%lu gaps=%lu overruns=%lu\n",
          rms,(unsigned long)peak,MILO_MODEL_ID,(unsigned long)milo.abortedClips,
          (unsigned long)milo.readGaps,(unsigned long)milo.computeOverruns);
        lastPrint=millis();
      }
    }
  }
}

bool publishMicrophone(const MicSample &sample) {
  char payload[500], distance[32];
  if (sample.wakeDistance<1e8f) snprintf(distance,sizeof(distance),"%.6f",sample.wakeDistance);
  else strcpy(distance,"null");
  const int length=snprintf(payload,sizeof(payload),
    "{\"schema_version\":1,\"type\":\"microphone_level\",\"source_id\":\"collar\","
    "\"seq\":%lu,\"timestamp_us\":%llu,\"sample_rate_hz\":16000,\"rms\":%.1f,"
    "\"peak\":%lu,\"valid\":%s,\"model_id\":\"%s\",\"wake_distance\":%s,"
    "\"wake_threshold\":%.6f,\"aborted_clips\":%lu,\"read_gaps\":%lu,\"compute_overruns\":%lu,\"busy_ms\":%lu,\"free_heap\":%lu}",
    (unsigned long)sample.sequence,(unsigned long long)sample.timestampUs,sample.rms,
    (unsigned long)sample.peak,sample.valid?"true":"false",MILO_MODEL_ID,distance,
    MILO_THRESHOLD,(unsigned long)sample.abortedClips,(unsigned long)sample.readGaps,
    (unsigned long)sample.computeOverruns,(unsigned long)(sample.busyFrames*20),
    (unsigned long)ESP.getFreeHeap());
  return length>0 && length<int(sizeof(payload)) && mqtt.publish(MIC_TOPIC,payload,false);
}

// Called only by networkTask: one MQTT PUBLISH contains a whole RIFF/WAV.
// No other MQTT operation may interleave between beginPublish and endPublish.
bool publishWav(const MiloCapture::Clip &clip) {
  if (!clip.frames || clip.frames>MiloCapture::MAX_FRAMES) return false;
  char topic[100];
  snprintf(topic,sizeof(topic),"sensor/collar/voice/wav/%08lx/%lu",
           (unsigned long)clip.session,(unsigned long)clip.id);
  uint8_t header[44];MiloCapture::wavHeader(header,clip.frames);
  const uint32_t bytes=44+clip.frames*MiloCapture::FRAME_BYTES;
  const uint32_t started=millis();
  if (!mqtt.beginPublish(topic,bytes,false)) return false;
  if (mqtt.write(header,sizeof(header))!=sizeof(header)) return false;
  for (uint32_t i=0;i<clip.frames;++i) {
    if (millis()-started>8000 || WiFi.status()!=WL_CONNECTED) return false;
    if (mqtt.write(milo.frame(clip,i),MiloCapture::FRAME_BYTES)!=MiloCapture::FRAME_BYTES)
      return false;
    // Let the continuous microphone reader/idle task run. This is still ONE MQTT message.
    if (i%8==7) vTaskDelay(pdMS_TO_TICKS(1));
  }
  if (!mqtt.endPublish()) return false;
  Serial.printf("# WAV written: %s bytes=%lu upload_ms=%lu truncated=%s\n",
     topic,(unsigned long)bytes,(unsigned long)(millis()-started),clip.truncated?"true":"false");
  // Optional metadata is separate; the WAV is independently usable without it.
  char info[650];
  int n=snprintf(info,sizeof(info),
    "{\"schema_version\":2,\"type\":\"voice_candidate\",\"source_id\":\"collar\","
    "\"wav_topic\":\"%s\",\"session_id\":%lu,\"clip_id\":%lu,"
    "\"timestamp_us\":%llu,\"model_id\":\"%s\",\"distance\":%.6f,"
    "\"sample_rate_hz\":16000,\"format\":\"wav_pcm_s16le\","
    "\"duration_ms\":%lu,\"wav_bytes\":%lu,\"truncated\":%s}",
    topic,(unsigned long)clip.session,(unsigned long)clip.id,
    (unsigned long long)clip.timestampUs,MILO_MODEL_ID,clip.distance,
    (unsigned long)(clip.frames*20),(unsigned long)bytes,clip.truncated?"true":"false");
  return n>0 && n<int(sizeof(info)) && mqtt.publish("sensor/collar/voice/event",info,false);
}

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
  if (!mqtt.setBufferSize(1024)) {
    Serial.println("# ERROR: MQTT buffer allocation failed");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  // Keep-alive leaves headroom for one bounded WAV send.
  mqtt.setKeepAlive(15);
  wifiClient.setTimeout(1000);
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

      // Drop completed offline clips; active captures abort on link epoch change.
      milo.setOnline(false);
      milo.discardReady();

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
        milo.setOnline(false);
      milo.discardReady();
        // Slow LED blink: Wi-Fi works, MQTT does not.
        if (now - lastLedToggle >= 1000) {
          lastLedToggle = now;
          ledState = !ledState;
          digitalWrite(LED_BUILTIN, ledState);
        }

        if (now - lastMqttAttempt >= MQTT_RETRY_MS) {
          lastMqttAttempt = now;

          char clientId[40];
          snprintf(clientId,sizeof(clientId),"collar-%012llx",
                   (unsigned long long)ESP.getEfuseMac());

          Serial.print("# MQTT connection attempt to ");
          Serial.println(MQTT_BROKER_IP);

          if (mqtt.connect(
                clientId,
                CONNECTION_TOPIC,
                1,
                true,
                CONNECTION_OFFLINE_PAYLOAD)) {

            if (mqtt.publish(
                  CONNECTION_TOPIC,
                  CONNECTION_ONLINE_PAYLOAD,
                  true)) {

              // Discard old level summaries after reconnect.

              xQueueReset(micQueue);

              milo.setOnline(true);
              Serial.printf("# MQTT connected; free_heap=%lu\n",(unsigned long)ESP.getFreeHeap());
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

        MicSample micSample;
        if (xQueueReceive(micQueue, &micSample, 0) == pdTRUE) {
          if (!publishMicrophone(micSample)) {
            forceMqttReconnect();
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
          }
        }

        MiloCapture::Clip clip;
        if (milo.take(clip)) {
          const bool ok=milo.fresh(clip) && publishWav(clip);
          milo.release(); // microphone may reuse audio memory only now
          if (!ok) {
            Serial.println("# WAV dropped/send failed; no automatic replay");
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

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_BUILTIN,OUTPUT);
  digitalWrite(LED_BUILTIN,LOW);
  micQueue=xQueueCreate(1,sizeof(MicSample));
  if (!micQueue || !milo.begin(esp_random())) {
    Serial.println("# ERROR: 128 kB audio storage allocation failed; not starting");
    while (true) delay(1000);
  }
  microphone.setPins(MIC_BCLK,MIC_WS,-1,MIC_SD);
  if (!microphone.begin(I2S_MODE_STD,MIC_RATE,I2S_DATA_BIT_WIDTH_32BIT,
                         I2S_SLOT_MODE_MONO,I2S_STD_SLOT_LEFT)) {
    Serial.println("# ERROR: INMP441 initialization failed");
    while (true) delay(1000);
  }
  Serial.printf("# Collar microphone ready; model=%s; free_heap=%lu\n",
                MILO_MODEL_ID,(unsigned long)ESP.getFreeHeap());
  if (MILO_COUNT==0)
    Serial.println("# UNTRAINED: levels work; no voice clips until enrollment and re-upload.");
  if (xTaskCreatePinnedToCore(microphoneTask,"collarAudio",8192,nullptr,2,nullptr,1)!=pdPASS ||
      xTaskCreatePinnedToCore(networkTask,"collarNetwork",8192,nullptr,1,nullptr,0)!=pdPASS) {
    Serial.println("# ERROR: task creation failed; reset after checking memory");
    while (true) delay(1000);
  }
}
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
