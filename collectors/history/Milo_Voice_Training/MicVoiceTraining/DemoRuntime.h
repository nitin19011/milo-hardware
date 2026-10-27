#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <atomic>
#include <math.h>
static std::atomic<bool> deviceBusy{false},clockUpdating{false},linkOnline{false};
#include "DemoClock.h"
#include "DemoMqtt.h"

static const uint32_t HOLD_MS=2000,BUZZ_MS=1000,RECORD_MS=3000,END_BUZZ_MS=1000;
static const uint32_t AUDIO_HZ=16000,AUDIO_SAMPLES=48000,GLOVE_HZ=50,GLOVE_SAMPLES=150;
static const char *HAND_PROFILE="glove-mpu6050-three-binary-demo-v1";
static const char *AUDIO_PROFILE="audio-wav-pcm16-mono-16k-demo-v1";
struct Job {
  char id[33]={},handBoot[33]={};int64_t startMs=0,startUs=0,deadlineMs=0,uploadMs=0;
  ClockMap clock;uint32_t clockError=0;
};
struct Control { char topic[96];uint16_t size;char body[2048]; };
static QueueHandle_t controlQueue;
static char bootId[33],streamId[33],clientId[24];
static uint32_t topicSeq[8]={};
static std::atomic<uint32_t> controlDrops{0};
static WiFiClientSecure tlsSocket;
static WiFiClient plainSocket;
static DemoMqtt mqtt(USE_TLS?static_cast<Client&>(tlsSocket):static_cast<Client&>(plainSocket));
static uint32_t droppedCaptures=0;

// Implemented by each device app. These callbacks execute in the network task.
static void deviceNetworkTick();
static void deviceConnected();
static void deviceDisconnected();
static void deviceOfflineTick();
static void fillMeta(JsonObject data);
static const char *captureState();

static void randomId(char *out){for(int i=0;i<4;i++)sprintf(out+i*8,"%08lx",(unsigned long)esp_random());out[32]=0;}
static bool validId(const char *v){if(!v||strlen(v)!=32)return false;for(int i=0;i<32;i++)if(!((v[i]>='0'&&v[i]<='9')||(v[i]>='a'&&v[i]<='f')))return false;return true;}
static String topic(const char *suffix){return String("milo/v1/")+SESSION+"/"+suffix;}
static JsonDocument envelope(const char *type,int slot,int64_t timeUs=-1,int64_t localUs=-1){
  JsonDocument d;d["version"]=1;d["type"]=type;d["source_id"]=SOURCE_ID;d["boot_id"]=bootId;d["stream_id"]=streamId;d["seq"]=topicSeq[slot]++;
  if(timeUs<0)timeUs=utcUs();if(localUs<0)localUs=esp_timer_get_time();
  if(timeUs)d["timestamp_ms"]=timeUs/1000;else d["timestamp_ms"]=nullptr;
  d["capture_us"]=localUs;if(clockValid())d["clock_uncertainty_ms"]=(clockErrorUs(clockSnapshot())+999)/1000;else d["clock_uncertainty_ms"]=nullptr;
  d["timestamp_domain"]="device_monotonic_ms";d["data"].to<JsonObject>();return d;
}
static bool sendJson(const char *suffix,JsonDocument &doc,bool retained=false,int64_t deadline=0){if(doc.overflowed())return false;String s;if(!s.reserve(measureJson(doc)+1))return false;serializeJson(doc,s);return mqtt.publish(topic(suffix).c_str(),s,retained,deadline);}
static bool sameJob(JsonVariantConst data,const Job &j){const char *id=data["capture_id"]|"";return j.id[0]&&!strcmp(id,j.id);}
static void jobData(JsonObject data,const Job &j){data["capture_id"]=j.id;data["trigger_source_id"]=HAND_ID;data["trigger_boot_id"]=j.handBoot;data["capture_start_ms"]=j.startMs;data["duration_ms"]=RECORD_MS;data["expires_at_ms"]=j.deadlineMs;}
static bool readJob(JsonDocument &doc,Job &j){
  auto data=doc["data"];const char *id=data["capture_id"]|"",*hand=doc["boot_id"]|"",*source=doc["source_id"]|"";
  if(doc["version"]!=1||strcmp(source,HAND_ID)||!validId(id)||!validId(hand)||strcmp(data["target_source_id"]|"",MIC_ID)||data["duration_ms"]!=RECORD_MS)return false;
  if(data["start_delay_ms"]!=3000)return false;
  auto c=clockSnapshot();
  int64_t start=(esp_timer_get_time()+3000000+999)/1000,deadline=start+18000;
  strcpy(j.id,id);strcpy(j.handBoot,hand);j.startMs=start;j.startUs=start*1000-c.offsetUs;j.deadlineMs=deadline;j.uploadMs=start+RECORD_MS+END_BUZZ_MS;j.clock=c;j.clockError=clockErrorUs(c);return true;
}
static void statusMessage(){
  auto d=envelope("device.status",0);d["client_id"]=clientId;d["state"]=clockValid()?"online":"degraded";
  auto h=d["health"].to<JsonObject>();h["capture"]=captureState();h["clock"]="local_relative";h["captures_dropped_total"]=droppedCaptures;h["control_queue_drops"]=controlDrops.load();h["free_heap"]=ESP.getFreeHeap();h["minimum_free_heap"]=ESP.getMinFreeHeap();
  sendJson((String("status/")+clientId).c_str(),d,true);
}
static void metaMessage(){auto d=envelope(IS_GLOVE?"hand.meta":"mic.meta",1);fillMeta(d["data"].as<JsonObject>());sendJson(IS_GLOVE?"hand/meta":"mic/meta",d,true);}
static bool configReady(){return strlen(WIFI_SSID)&&strlen(WIFI_PASSWORD)&&(!USE_TLS||strstr(ROOT_CA,"BEGIN CERTIFICATE"))&&(USE_TLS||ALLOW_LOCAL_PLAINTEXT);}
static void networkTask(void*){
  WiFi.persistent(false);WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.setAutoReconnect(true);
  int64_t nextWifi=0,nextConnect=0,nextClock=0,lastStatus=0,lastConfigLog=0;uint32_t backoff=1000;
  mqtt.handler=[](const char *t,const uint8_t *p,size_t n,bool retained){
    if(retained||n>=sizeof(Control::body)||strlen(t)>=sizeof(Control::topic))return;
    Control c{};strcpy(c.topic,t);c.size=n;memcpy(c.body,p,n);c.body[n]=0;
    if(xQueueSend(controlQueue,&c,0)!=pdTRUE)++controlDrops;
  };
  for(;;){
    int64_t now=esp_timer_get_time();
    if(!mqtt.online&&linkOnline.exchange(false))deviceDisconnected();
    if(!linkOnline)deviceOfflineTick();
    if(!configReady()){if(now-lastConfigLog>10000000||!lastConfigLog){Serial.println("# Configuration pending: fill Wi-Fi, role password and CA, then run configure_demo.py. Capture is disabled.");lastConfigLog=now;}delay(100);continue;}
    if(WiFi.status()!=WL_CONNECTED){
      if(linkOnline.exchange(false)){mqtt.close();deviceDisconnected();}
      if(now>=nextWifi){WiFi.disconnect();WiFi.begin(WIFI_SSID,WIFI_PASSWORD);nextWifi=now+20000000;Serial.println("# Connecting Wi-Fi");}
      delay(20);continue;
    }
    if(!deviceBusy&&!clockUpdating&&now>=nextClock){clockUpdating=true;bool ok=syncClock();clockUpdating=false;nextClock=esp_timer_get_time()+(ok?64000000:15000000);if(!ok)Serial.println("# Time sync unavailable/uncertain; capture disabled until clock is usable.");}
    if(!clockValid()){if(linkOnline.exchange(false)){mqtt.close();deviceDisconnected();}delay(20);continue;}
    if(!mqtt.online&&now>=nextConnect){
      mqtt.close();randomId(streamId);memset(topicSeq,0,sizeof(topicSeq));bool connected;
      if(USE_TLS){tlsSocket.setCACert(ROOT_CA);tlsSocket.setHandshakeTimeout(8);tlsSocket.setTimeout(2000);connected=tlsSocket.connect(MQTT_HOST,MQTT_PORT);}
      else {plainSocket.setTimeout(2000);connected=plainSocket.connect(MQTT_HOST,MQTT_PORT,1500);}
      String will=String("{\"version\":1,\"type\":\"device.status\",\"source_id\":\"")+SOURCE_ID+"\",\"boot_id\":\""+bootId+"\",\"client_id\":\""+clientId+"\",\"state\":\"offline\",\"timestamp_ms\":null}";
      if(connected&&mqtt.connect(clientId,MQTT_USERNAME,MQTT_PASSWORD,topic((String("status/")+clientId).c_str()).c_str(),will.c_str())){
        bool subscribed=IS_GLOVE?(mqtt.subscribe(topic("mic/results").c_str())&&mqtt.subscribe(topic("hand/feedback").c_str())):mqtt.subscribe(topic("mic/capture").c_str());
        if(subscribed){linkOnline=true;backoff=1000;deviceConnected();metaMessage();statusMessage();lastStatus=now;Serial.printf("# MQTT online: %s\n",SOURCE_ID);}else mqtt.close();
      }
      if(!mqtt.online){nextConnect=esp_timer_get_time()+int64_t(backoff+esp_random()%300)*1000;backoff=min(backoff*2,uint32_t(15000));Serial.printf("# MQTT connection failed: %s\n",mqtt.error);}
    }
    if(mqtt.online){mqtt.poll();if(!mqtt.online){if(linkOnline.exchange(false))deviceDisconnected();nextConnect=esp_timer_get_time()+1000000;}else{deviceNetworkTick();if(!deviceBusy&&now-lastStatus>=5000000){statusMessage();metaMessage();lastStatus=now;}}}
    delay(2);
  }
}
static void runtimeSetup(){
  Serial.begin(115200);delay(300);randomId(bootId);randomId(streamId);
  snprintf(clientId,sizeof(clientId),"%s%08lx",IS_GLOVE?"hand":"mic",(unsigned long)esp_random());
  pinMode(LED_BUILTIN,OUTPUT);digitalWrite(LED_BUILTIN,LOW);controlQueue=xQueueCreate(4,sizeof(Control));
  if(!controlQueue){Serial.println("# FATAL: control queue allocation");while(true)delay(1000);}
}
static void startNetwork(){if(xTaskCreatePinnedToCore(networkTask,"demoNetwork",10000,nullptr,1,nullptr,0)!=pdPASS){Serial.println("# FATAL: network task allocation");while(true)delay(1000);}}
