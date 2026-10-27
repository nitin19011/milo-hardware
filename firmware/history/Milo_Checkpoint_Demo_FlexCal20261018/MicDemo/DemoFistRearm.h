#pragma once
#include <stdint.h>

// Any finger dropping below the full-fist trigger is enough; no straight-finger
// state is required. Latch a brief release, including during the recorded action.
struct DemoFistRearm {
  bool ready=false,tracking=false;
  uint32_t sinceMs=0;
  void consume(){ready=false;tracking=false;}
  void observe(bool fullFist,bool healthy,uint32_t nowMs){
    if(ready)return;
    if(fullFist||!healthy){tracking=false;return;}
    if(!tracking){tracking=true;sinceMs=nowMs;}
    if(uint32_t(nowMs-sinceMs)>=200)ready=true;
  }
};
