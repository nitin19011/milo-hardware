#pragma once
#include <stdint.h>
#include <stddef.h>
// Continuous PCM history. Absolute sample indices prevent stale data after an I2S gap.
struct VoiceHistory {
  static constexpr size_t capacity=4800;
  int16_t samples[capacity]={};size_t available=0;int64_t endIndex=0;
  void push(int64_t firstIndex,const int32_t *raw,size_t count){
    if(firstIndex!=endIndex)available=0;
    for(size_t i=0;i<count;i++){
      int32_t v=(raw[i]>>16)*4;
      samples[(firstIndex+int64_t(i))%capacity]=int16_t(v>32767?32767:(v< -32768?-32768:v));
    }
    available=available+count>capacity?capacity:available+count;endIndex=firstIndex+count;
  }
  bool contains(int64_t first,int64_t end)const{return first>=endIndex-int64_t(available)&&first<=end&&end<=endIndex;}
  int16_t at(int64_t index)const{return samples[index%capacity];}
};
