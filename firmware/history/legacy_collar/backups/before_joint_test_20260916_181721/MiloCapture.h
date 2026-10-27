#pragma once
#include <Arduino.h>
#include <esp_timer.h>
#include <atomic>
#include "MiloMatcher.h"

// One clip, stored in four 32 kB blocks: no contiguous 128 kB allocation needed.
// Idle history occupies the SAME blocks as the final clip; no second audio copy.
class MiloCapture {
 public:
  static constexpr uint32_t FRAME_SAMPLES=320, FRAME_BYTES=640;
  static constexpr uint32_t HISTORY=70, POST_LIMIT=130, MAX_FRAMES=200;
  struct Clip {
    uint32_t session, id, frames, preFrames, preStart, epoch, readyMs;
    uint64_t timestampUs;
    float distance;
    bool truncated;
  };
 private:
  enum Phase { IDLE, CAPTURING, READY, SENDING, RESET };
  std::atomic<int> phase{IDLE};
  std::atomic<bool> online{false};
  std::atomic<uint32_t> epoch{0};
  uint8_t *blocks[4]={};
  Clip clip{};
  uint32_t session=0, nextId=0, head=0, filled=0, silence=0, post=0;
  MiloMatcher matcher;
  uint8_t *physical(uint32_t frame) {
    return blocks[frame/50]+(frame%50)*FRAME_BYTES;
  }
  void resetCapture() {
    head=filled=silence=post=0;
    matcher.reset();
    phase.store(IDLE);
  }
 public:
  uint32_t readGaps=0, computeOverruns=0, abortedClips=0, busyFrames=0;
  float bestSinceStatus=1e9f;

  bool begin(uint32_t bootId) {
    session=bootId;
    for (int i=0;i<4;++i) {
      blocks[i]=static_cast<uint8_t *>(malloc(50*FRAME_BYTES));
      if (!blocks[i]) {
        for (int j=0;j<i;++j) { free(blocks[j]);blocks[j]=nullptr; }
        return false;
      }
    }
    matcher.reset();
    return true;
  }
  // Network task owns link changes. The epoch invalidates captures spanning an outage.
  void setOnline(bool value) {
    if (online.load()!=value) {
      epoch.fetch_add(1);
      online.store(value);
    }
  }
  bool connected() const { return online.load(); }
  bool fresh(const Clip &c) const {
    return online.load() && c.epoch==epoch.load() && uint32_t(millis()-c.readyMs)<5000;
  }
  bool take(Clip &out) {
    int expected=READY;
    if (!phase.compare_exchange_strong(expected,SENDING)) return false;
    out=clip; return true;
  }
  void release() { phase.store(RESET); } // called ONLY after network has finished reading
  void discardReady() {
    int expected=READY;
    phase.compare_exchange_strong(expected,RESET);
  }
  const uint8_t *frame(const Clip &c,uint32_t i) {
    return physical(i<c.preFrames ? (c.preStart+i)%HISTORY : i);
  }
  static void put16(uint8_t *p,uint16_t v) { p[0]=v;p[1]=v>>8; }
  static void put32(uint8_t *p,uint32_t v) {
    for (int i=0;i<4;++i) p[i]=(v>>(8*i))&255;
  }
  static void wavHeader(uint8_t *out,uint32_t frames) {
    const uint32_t bytes=frames*FRAME_BYTES;
    memset(out,0,44);
    memcpy(out,"RIFF",4);put32(out+4,36+bytes);
    memcpy(out+8,"WAVEfmt ",8);put32(out+16,16);
    put16(out+20,1);put16(out+22,1);put32(out+24,16000);
    put32(out+28,32000);put16(out+32,2);put16(out+34,16);
    memcpy(out+36,"data",4);put32(out+40,bytes);
  }
  void gap() {
    ++readGaps;
    int p=phase.load();
    // Never touch a completed buffer owned by the network task.
    if (p==IDLE || p==CAPTURING || p==RESET) {
      if (p==CAPTURING) ++abortedClips;
      resetCapture();
    }
  }
  void feed(const int16_t *pcm,float rms) {
    const uint64_t before=esp_timer_get_time();
    int p=phase.load();
    if (p==RESET) { resetCapture();p=IDLE; }
    if (p==READY || p==SENDING) { ++busyFrames;return; }
    if (p==CAPTURING && (!online.load() || clip.epoch!=epoch.load())) {
      ++abortedClips;resetCapture();p=IDLE;
    }
    if (p==CAPTURING) {
      memcpy(physical(clip.frames++),pcm,FRAME_BYTES);
      ++post;
      silence=rms<MILO_ENERGY_FLOOR ? silence+1 : 0;
      if (silence>=30 || post>=POST_LIMIT) {
        clip.truncated=post>=POST_LIMIT;
        clip.readyMs=millis();
        phase.store(READY); // release publishes immutable data/metadata to network
        matcher.reset();
      }
    } else {
      memcpy(physical(head),pcm,FRAME_BYTES);
      head=(head+1)%HISTORY;
      if (filled<HISTORY) ++filled;
      const float score=matcher.feed(pcm,rms);
      if (score<bestSinceStatus) bestSinceStatus=score;
      if (MILO_COUNT>0 && score<=MILO_THRESHOLD && online.load()) {
        clip.session=session;clip.id=++nextId;
        clip.frames=clip.preFrames=filled;
        clip.preStart=(head+HISTORY-filled)%HISTORY;
        clip.epoch=epoch.load();clip.distance=score;clip.truncated=false;
        const uint64_t historyUs=uint64_t(filled)*20000;
        clip.timestampUs=before>historyUs ? before-historyUs : 0;
        post=silence=0;
        phase.store(CAPTURING);
      }
    }
    if (esp_timer_get_time()-before>20000) ++computeOverruns;
  }
};
