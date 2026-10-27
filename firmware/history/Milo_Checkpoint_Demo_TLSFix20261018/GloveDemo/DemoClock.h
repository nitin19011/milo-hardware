#pragma once
#include <Arduino.h>
#include <WiFiUdp.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <sys/time.h>
#include <atomic>

// A capture freezes this UTC-to-monotonic mapping. No clock stepping during captures.
struct ClockMap { int64_t offsetUs=0, checkedUs=0; uint32_t uncertaintyUs=0, generation=0; };
static portMUX_TYPE clockMux=portMUX_INITIALIZER_UNLOCKED;
static ClockMap currentClock;
static uint32_t be32(const uint8_t *p) { return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|p[3]; }
static int64_t ntpUs(const uint8_t *p) {
  uint32_t seconds=be32(p); if(seconds<2208988800UL) return 0; // This demo runs before NTP era rollover in 2036.
  return int64_t(seconds-2208988800UL)*1000000+(uint64_t(be32(p+4))*1000000>>32);
}
static ClockMap clockSnapshot() { portENTER_CRITICAL(&clockMux);auto v=currentClock;portEXIT_CRITICAL(&clockMux);return v; }
static uint32_t clockErrorUs(const ClockMap &c) {
  if(!c.generation)return UINT32_MAX;
  int64_t age=esp_timer_get_time()-c.checkedUs;
  // Conservative configured oscillator allowance: 100 ppm, plus the measured SNTP delay/root distance.
  return c.uncertaintyUs+uint32_t(max(int64_t(0),age)/10000);
}
static bool clockValid() { auto c=clockSnapshot();return clockErrorUs(c)<=MAX_CLOCK_ERROR_MS*1000 && esp_timer_get_time()-c.checkedUs<300000000LL; }
static int64_t utcUs() { auto c=clockSnapshot();return c.generation ? esp_timer_get_time()+c.offsetUs : 0; }
static bool syncClock() {
  ClockMap best; best.uncertaintyUs=UINT32_MAX;
  for(const char *host:NTP_SERVERS) {
    IPAddress ip;if(!WiFi.hostByName(host,ip))continue;
    WiFiUDP udp;if(!udp.begin(0))continue;
    uint8_t request[48]={0};request[0]=0x23; // v4 client; originate nonce verified on response.
    for(int i=40;i<48;i++)request[i]=uint8_t(esp_random());
    int64_t sent=esp_timer_get_time();udp.beginPacket(ip,123);udp.write(request,48);udp.endPacket();
    int bytes=0;while(esp_timer_get_time()-sent<1500000 && !(bytes=udp.parsePacket()))delay(5);
    int64_t received=esp_timer_get_time();uint8_t reply[48];
    bool ok=bytes>=48 && udp.remoteIP()==ip && udp.remotePort()==123 && udp.read(reply,48)==48;udp.stop();
    if(!ok || (reply[0]&7)!=4 || ((reply[0]>>3)&7)<3 || (reply[0]>>6)==3 || reply[1]==0 || reply[1]>15 || memcmp(reply+24,request+40,8))continue;
    int64_t t2=ntpUs(reply+32),t3=ntpUs(reply+40),rtt=received-sent;
    if(t2<1735689600000000LL || t3<t2 || t3-t2>rtt+2000)continue;
    int64_t rootDelay=int32_t(be32(reply+4));
    uint64_t root=uint64_t(be32(reply+8))*1000000/65536 + uint64_t(max(int64_t(0),rootDelay))*1000000/131072;
    uint64_t error=uint64_t(rtt)/2+root+2000;
    if(error>=best.uncertaintyUs)continue;
    best.offsetUs=((t2-sent)+(t3-received))/2;best.checkedUs=received;best.uncertaintyUs=uint32_t(error);
  }
  if(best.uncertaintyUs>MAX_CLOCK_ERROR_MS*1000)return false;
  portENTER_CRITICAL(&clockMux);
  if(deviceBusy){portEXIT_CRITICAL(&clockMux);return false;}
  best.generation=currentClock.generation+1;currentClock=best;portEXIT_CRITICAL(&clockMux);
  int64_t epoch=esp_timer_get_time()+best.offsetUs;timeval tv{time_t(epoch/1000000),suseconds_t(epoch%1000000)};settimeofday(&tv,nullptr);
  Serial.printf("# Clock synchronized; estimated uncertainty %.1f ms\n",best.uncertaintyUs/1000.0);
  return true;
}
