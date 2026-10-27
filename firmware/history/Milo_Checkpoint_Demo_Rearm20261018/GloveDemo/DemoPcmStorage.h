#pragma once
#include <stdint.h>
#include <stddef.h>
// Packed pairs preserve PCM16 exactly while allowing ESP32 word-only (IRAM) heap.
// Never cast these blocks to bytes/int16_t or pass them directly to TLS: ESP32
// IRAM permits aligned 32-bit loads/stores only. copyBytes is the byte bridge.
// Allocation/release happen on the network task, with audio ownership held outside.
template<size_t Count,size_t Samples> struct DemoPcmStorage {
  static_assert(Samples%2==0,"PCM blocks contain whole packed words");
  static constexpr size_t byteSize=Count*Samples*2;
  uint32_t *blocks[Count]={};
  size_t failureBlock=Count;
  bool allocate(void *(*alloc)(size_t),void (*freeBlock)(void*)){
    failureBlock=Count;
    for(size_t i=0;i<Count;i++)if(!blocks[i]){
      blocks[i]=static_cast<uint32_t*>(alloc(Samples*2));
      if(!blocks[i]){failureBlock=i;release(freeBlock);return false;}
      volatile uint32_t *words=blocks[i];
      for(size_t w=0;w<Samples/2;w++)words[w]=0;
    }
    return true;
  }
  void setSample(size_t index,int16_t value){
    volatile uint32_t *p=blocks[index/Samples]+(index%Samples)/2;
    const uint32_t v=uint16_t(value);
    if(index%2)*p=(*p&0x0000ffffu)|(v<<16);
    else *p=(*p&0xffff0000u)|v;
  }
  bool copyBytes(size_t offset,uint8_t *dest,size_t bytes) const {
    if(offset>byteSize||bytes>byteSize-offset)return false;
    while(bytes){
      const size_t block=offset/(Samples*2),inBlock=offset%(Samples*2);
      if(!blocks[block])return false;
      const volatile uint32_t *p=blocks[block]+inBlock/4;
      const uint32_t word=*p;
      for(size_t shift=inBlock%4;shift<4&&bytes;shift++,offset++,bytes--)
        *dest++=uint8_t(word>>(shift*8));
    }
    return true;
  }
  static bool readBytes(const void *context,size_t offset,uint8_t *dest,size_t bytes){
    return static_cast<const DemoPcmStorage*>(context)->copyBytes(offset,dest,bytes);
  }
  void release(void (*freeBlock)(void*)){
    for(auto &block:blocks)if(block){freeBlock(block);block=nullptr;}
  }
};
