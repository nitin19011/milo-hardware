#pragma once
#include <stdint.h>
// Live mic/meta messages only: a retained record is not proof the mic is still online.
struct DemoMicReadiness {
  bool seen=false,compatible=false,audioReady=false,clockReady=false;
  uint32_t receivedMs=0;
  const char *reason(uint32_t now)const{
    if(!seen)return "MIC_NOT_SEEN";
    if(uint32_t(now-receivedMs)>15000)return "MIC_HEARTBEAT_EXPIRED";
    if(!compatible)return "MIC_PROFILE_MISMATCH";
    if(!clockReady)return "MIC_CLOCK_UNSYNCED";
    if(!audioReady)return "MIC_NOT_READY";
    return "READY";
  }
  bool ready(uint32_t now)const{return reason(now)[0]=='R';}
};
inline const char *demoHoldFailure(bool link,bool clock,uint8_t sensorFaults,bool fist,bool prepareFailed){
  if(!link)return "MQTT_DISCONNECTED";
  if(!clock)return "CLOCK_NOT_READY";
  if(sensorFaults)return "SENSOR_FAULT_DURING_HOLD";
  if(!fist)return "FIST_RELEASED_BEFORE_CUE";
  if(prepareFailed)return "PREPARE_PUBLISH_FAILED";
  return nullptr;
}
