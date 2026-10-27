#pragma once
#include <stdint.h>
// UNTRAINED placeholder. Replaced by: py milo.py train
// Microphone level reporting works; no wake candidates are generated yet.
static constexpr int MILO_COUNT = 0;
static constexpr int MILO_MAX_FRAMES = 1;
static constexpr float MILO_THRESHOLD = 0.0f;
static constexpr float MILO_ENERGY_FLOOR = 8.0f;
static const char MILO_MODEL_ID[] = "untrained";
static const float MILO_WINDOW[320] = {};
static const float MILO_MEL[20][257] = {};
static const float MILO_DCT[12][20] = {};
static const int8_t MILO_EMPTY[12] = {};
static const int8_t * const MILO_TEMPLATES[1] = {MILO_EMPTY};
static const int MILO_LENGTHS[1] = {1};
