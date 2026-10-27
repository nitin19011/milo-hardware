#pragma once
#include <Arduino.h>
#include <esp_timer.h>
// Voice-only collection uses one device's monotonic clock, without NTP or UTC synchronisation.
struct ClockMap { int64_t offsetUs=0,checkedUs=0;uint32_t uncertaintyUs=0,generation=1; };
static portMUX_TYPE clockMux=portMUX_INITIALIZER_UNLOCKED;
static ClockMap currentClock;
static ClockMap clockSnapshot(){return currentClock;}
static uint32_t clockErrorUs(const ClockMap&){return 0;} // Local counter, not cross-device UTC accuracy.
static bool clockValid(){return true;}
static int64_t utcUs(){return esp_timer_get_time();} // Legacy name; timestamp_domain declares device_monotonic_ms.
static bool syncClock(){return true;}
