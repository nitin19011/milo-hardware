#pragma once
#include <stdint.h>
#include <stddef.h>
// Allocated only after TLS/MQTT connects, freeing transient handshake memory first.
template<size_t Count,size_t Samples> struct DemoPcmStorage {
  int16_t *blocks[Count]={};
  bool allocate(void *(*alloc)(size_t),void (*freeBlock)(void*)){
    for(size_t i=0;i<Count;i++)if(!blocks[i]){
      blocks[i]=static_cast<int16_t*>(alloc(Samples*sizeof(int16_t)));
      if(!blocks[i]){release(freeBlock);return false;}
    }
    return true;
  }
  void release(void (*freeBlock)(void*)){
    for(auto &block:blocks)if(block){freeBlock(block);block=nullptr;}
  }
};
