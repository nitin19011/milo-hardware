#pragma once
#include <Arduino.h>
#include <esp_timer.h>
#include "MiloMatcher.h"

// Finite queue: no network operation runs in the microphone task.
// QoS 0 delivery is checked by clip indices and an end-to-end CRC on the laptop.
struct VoicePacket {
  bool audio;
  uint16_t length;
  uint8_t data[700];
};
QueueHandle_t voiceQueue;
const char VOICE_EVENT_TOPIC[] = "sensor/collar/voice/event";
const char VOICE_AUDIO_TOPIC[] = "sensor/collar/voice/audio";

class MiloCapture {
  static constexpr int HISTORY=70; // 1.4 seconds, includes the detected word
  int16_t history[HISTORY][320];
  int head=0, filled=0;
  MiloMatcher matcher;
  bool active=false;
  uint32_t session=0,clip=0,index=0,crc=0xffffffffU;
  uint32_t postFrames=0,silence=0;
  bool incomplete=false;
  uint64_t startUs=0;
  float distance=0;
  VoicePacket packet;
  bool push() {
    if (xQueueSend(voiceQueue,&packet,0)==pdTRUE) return true;
    ++queueDrops; incomplete=true; return false;
  }
  void put32(int offset,uint32_t value) {
    for (int i=0;i<4;++i) packet.data[offset+i]=(value>>(8*i))&255;
  }
  void audio(const int16_t *pcm) {
    packet.audio=true;packet.length=660;
    memcpy(packet.data,"MLA1",4);
    put32(4,session);put32(8,clip);put32(12,index++);put32(16,320);
    memcpy(packet.data+20,pcm,640);
    for (int i=0;i<640;++i) {
      crc^=packet.data[20+i];
      for (int b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xedb88320U:0);
    }
    push();
  }
  void event(bool finished, bool truncated=false) {
    packet.audio=false;
    int n=snprintf(reinterpret_cast<char *>(packet.data),sizeof(packet.data),
      "{\"schema_version\":1,\"type\":\"%s\",\"source_id\":\"collar\","
      "\"session_id\":%lu,\"clip_id\":%lu,\"timestamp_us\":%llu,"
      "\"model_id\":\"%s\",\"trigger\":\"milo_template\",\"distance\":%.6f,"
      "\"threshold\":%.6f,\"sample_rate_hz\":16000,\"format\":\"pcm_s16le\","
      "\"frames\":%lu,\"duration_ms\":%lu,\"crc32\":%lu,"
      "\"complete\":%s,\"truncated\":%s}",
      finished?"voice_candidate":"wake_candidate",(unsigned long)session,
      (unsigned long)clip,(unsigned long long)startUs,MILO_MODEL_ID,
      distance,MILO_THRESHOLD,(unsigned long)index,(unsigned long)(index*20),
      (unsigned long)(crc^0xffffffffU),finished&&!incomplete?"true":"false",
      truncated?"true":"false");
    if (n<=0 || n>=int(sizeof(packet.data))) { incomplete=true;++queueDrops;return; }
    packet.length=n;
    if (!push()) Serial.println("# Voice event dropped: MQTT queue full");
  }
 public:
  uint32_t queueDrops=0,readGaps=0,computeOverruns=0;
  float bestSinceStatus=1e9f;
  void begin(uint32_t bootId) { session=bootId;matcher.reset(); }
  void gap() {
    ++readGaps;
    if (active) { incomplete=true;event(true);active=false; }
    matcher.reset();filled=0;head=0;
  }
  void feed(const int16_t *pcm,float rms) {
    uint64_t before=esp_timer_get_time();
    memcpy(history[head],pcm,640); head=(head+1)%HISTORY;
    if (filled<HISTORY) ++filled;
    if (active) {
      audio(pcm); ++postFrames;
      silence = rms<MILO_ENERGY_FLOOR ? silence+1 : 0;
      // At least 0.3 s following the wake; finish on 0.6 s silence or 2.6 s cap.
      if ((postFrames>=15 && silence>=30) || postFrames>=130) {
        event(true,postFrames>=130); active=false;matcher.reset();
      }
    } else {
      float score=matcher.feed(pcm,rms);
      if (score<bestSinceStatus) bestSinceStatus=score;
      if (MILO_COUNT>0 && score<=MILO_THRESHOLD) {
        ++clip;index=0;crc=0xffffffffU;incomplete=false;distance=score;
        postFrames=silence=0;
        startUs=before-uint64_t(filled)*20000;
        event(false);
        for (int i=0;i<filled;++i) audio(history[(head-filled+i+HISTORY)%HISTORY]);
        active=true;
      }
    }
    if (esp_timer_get_time()-before>20000) ++computeOverruns;
  }
};
