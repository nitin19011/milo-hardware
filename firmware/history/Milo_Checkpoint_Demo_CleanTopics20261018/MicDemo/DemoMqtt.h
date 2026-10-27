#pragma once
#include <Arduino.h>
#include <Client.h>
#include <functional>

// Small MQTT 3.1.1 transport: QoS1, clean session, binary scatter/gather publish.
// It streams the frozen WAV without allocating a second 96kB outbox copy.
// Only the network task calls these methods. Callbacks enqueue work; never publish recursively.
class DemoMqtt {
 public:
  // Reader parts bridge memory which cannot be accessed as bytes (ESP32 IRAM).
  struct Part {
    const uint8_t *data; size_t size;
    bool (*reader)(const void*,size_t,uint8_t*,size_t)=nullptr;
    const void *context=nullptr;
  };
  using Handler=std::function<void(const char*,const uint8_t*,size_t,bool)>;
  explicit DemoMqtt(Client &client):socket(client){}
  Handler handler;
  bool online=false;
  const char *error="offline";
  void close(){online=false;socket.stop();transactionDeadline=0;resetRx();}
  bool connect(const char *id,const char *user,const char *password,const char *willTopic,const char *willText) {
    resetRx();online=false;uint8_t b[1500];size_t n=0;
    if(!putString(b,n,sizeof(b),"MQTT"))return false;b[n++]=4;
    b[n++]=0x02|0x04|0x08|0x20|(strlen(user)?0xC0:0); // clean, retained QoS1 will, optional credentials
    b[n++]=0;b[n++]=15;
    if(!putString(b,n,sizeof(b),id)||!putString(b,n,sizeof(b),willTopic)||!putString(b,n,sizeof(b),willText))return false;
    if(strlen(user)&&(!putString(b,n,sizeof(b),user)||!putString(b,n,sizeof(b),password)))return false;
    if(!header(0x10,n)||!writeAll(b,n))return false;
    connack=-1;int64_t end=esp_timer_get_time()+5000000;
    while(socket.connected()&&esp_timer_get_time()<end&&connack<0){poll();delay(1);}
    online=connack==0;if(!online){error="MQTT CONNECT rejected/timed out";close();}return online;
  }
  bool subscribe(const char *topic) {
    uint8_t b[300];size_t n=0;uint16_t id=nextId();b[n++]=id>>8;b[n++]=id;
    if(!putString(b,n,sizeof(b),topic))return false;b[n++]=1;
    suback=0;subcode=0x80;
    if(!header(0x82,n)||!writeAll(b,n))return false;
    int64_t end=esp_timer_get_time()+4000000;
    while(socket.connected()&&esp_timer_get_time()<end&&suback!=id){poll();delay(1);}
    if(suback!=id||subcode==0x80){error="MQTT subscription denied/timed out";close();return false;}return true;
  }
  bool publish(const char *topic,const uint8_t *p,size_t n,bool retain=false,int64_t deadline=0){Part part{p,n};return publishParts(topic,&part,1,retain,deadline);}
  bool publish(const char *topic,const String &s,bool retain=false,int64_t deadline=0){return publish(topic,reinterpret_cast<const uint8_t*>(s.c_str()),s.length(),retain,deadline);}
  bool publishParts(const char *topic,const Part *parts,size_t count,bool retain=false,int64_t deadline=0) {
    if(!online)return false;uint32_t size=0;for(size_t i=0;i<count;i++){if(parts[i].size>512*1024-size)return false;size+=uint32_t(parts[i].size);}
    size_t tlen=strlen(topic);if(tlen>240||size>512*1024)return false;
    uint16_t id=nextId();uint8_t prefix[246];prefix[0]=tlen>>8;prefix[1]=tlen;memcpy(prefix+2,topic,tlen);prefix[tlen+2]=id>>8;prefix[tlen+3]=id;
    puback=0;transactionDeadline=esp_timer_get_time()+12000000;if(deadline)transactionDeadline=min(transactionDeadline,deadline);
    if(!header(uint8_t(0x32|(retain?1:0)),size+tlen+4)||!writeAll(prefix,tlen+4))return fail("publish header");
    for(size_t i=0;i<count;i++)if(!writePart(parts[i]))return fail("publish data");
    int64_t end=min(esp_timer_get_time()+5000000,transactionDeadline);
    while(socket.connected()&&esp_timer_get_time()<end&&puback!=id){poll();delay(1);}
    if(puback!=id)return fail("PUBACK timed out");transactionDeadline=0;return true;
  }
  void poll() {
    if(!socket.connected()){online=false;return;}
    size_t budget=16384;
    while(socket.available()&&budget--) {
      int c=socket.read();if(c<0)break;uint8_t byte=c;lastIn=esp_timer_get_time();
      if(stage==0){rxType=byte;stage=1;remaining=0;multiplier=1;lenBytes=0;rxSince=lastIn;}
      else if(stage==1){remaining+=(byte&127)*multiplier;multiplier*=128;
        if(++lenBytes>4 || remaining>sizeof(rx)){fail("incoming packet too large");return;}
        if(!(byte&128)){used=0;stage=2;if(!remaining){dispatch();resetRx();}}}
      else {rx[used++]=byte;if(used==remaining){dispatch();resetRx();}}
    }
    int64_t now=esp_timer_get_time();
    if(stage&&now-rxSince>4000000){fail("partial packet timeout");return;}
    if(online&&now-lastOut>7000000){uint8_t p[2]={0xC0,0};if(!writeAll(p,2))fail("PING failed");}
    if(online&&now-lastIn>25000000)fail("broker silent");
  }
 private:
  Client &socket;uint8_t rx[8192];uint8_t rxType=0,stage=0,lenBytes=0;size_t used=0;uint32_t remaining=0,multiplier=1;
  int64_t lastOut=0,lastIn=0,rxSince=0,transactionDeadline=0;uint16_t counter=0,puback=0,suback=0;uint8_t subcode=0x80;int connack=-1;
  void resetRx(){stage=0;used=0;remaining=0;multiplier=1;}
  bool fail(const char *why){error=why;close();return false;}
  uint16_t nextId(){if(!++counter)++counter;return counter;}
  static bool putString(uint8_t *b,size_t &n,size_t cap,const char *s){size_t len=strlen(s);if(len>65535||n+len+2>cap)return false;b[n++]=len>>8;b[n++]=len;memcpy(b+n,s,len);n+=len;return true;}
  bool header(uint8_t type,uint32_t len){uint8_t b[5];size_t n=0;b[n++]=type;do{uint8_t v=len%128;len/=128;if(len)v|=128;b[n++]=v;}while(len);return writeAll(b,n);}
  bool writePart(const Part &part){
    if(!part.reader)return !part.size||(part.data&&writeAll(part.data,part.size));
    uint8_t scratch[1024]; // ordinary task stack/DRAM; TLS never reads word-only heap
    for(size_t offset=0;offset<part.size;){
      size_t bytes=min(sizeof(scratch),part.size-offset);
      if(!part.reader(part.context,offset,scratch,bytes)||!writeAll(scratch,bytes))return false;
      offset+=bytes;
    }
    return true;
  }
  bool writeAll(const uint8_t *p,size_t n) {
    int64_t end=esp_timer_get_time()+12000000;if(transactionDeadline)end=min(end,transactionDeadline);size_t offset=0;
    while(offset<n&&socket.connected()&&esp_timer_get_time()<end){size_t w=socket.write(p+offset,min(size_t(1024),n-offset));if(w){offset+=w;lastOut=esp_timer_get_time();}else delay(1);}
    return offset==n;
  }
  void dispatch() {
    uint8_t type=rxType>>4;
    if(type==2){if(remaining==2)connack=rx[1];return;}
    if(type==4){if(remaining==2)puback=(uint16_t(rx[0])<<8)|rx[1];return;}
    if(type==9){if(remaining>=3){suback=(uint16_t(rx[0])<<8)|rx[1];subcode=rx[2];}return;}
    if(type==13)return;
    if(type!=3||remaining<2)return;
    size_t topicLen=(size_t(rx[0])<<8)|rx[1],offset=2+topicLen;uint8_t qos=(rxType>>1)&3;
    if(!topicLen||topicLen>240||offset>remaining||qos>1){fail("invalid incoming PUBLISH");return;}
    char topic[241];memcpy(topic,rx+2,topicLen);topic[topicLen]=0;
    uint16_t id=0;if(qos){if(offset+2>remaining){fail("missing packet id");return;}id=(uint16_t(rx[offset])<<8)|rx[offset+1];offset+=2;}
    if(handler)handler(topic,rx+offset,remaining-offset,rxType&1);
    if(qos){uint8_t ack[4]={0x40,2,uint8_t(id>>8),uint8_t(id)};if(!writeAll(ack,4))fail("incoming PUBACK write");}
  }
};
