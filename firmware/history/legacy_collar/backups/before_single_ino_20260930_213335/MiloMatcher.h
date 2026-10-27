#pragma once
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "milo_model.h"

// 20 ms frames, 512-point FFT, 20 mel bands, 12 normalized cepstral features.
// The laptop uses the same math, quantized templates and DTW recurrence.
class MiloMatcher {
  static constexpr int T = MILO_COUNT ? MILO_COUNT : 1;
  float real[512], imag[512];
  float previous[T][MILO_MAX_FRAMES+1];
  uint32_t starts[T][MILO_MAX_FRAMES+1];
  float current[MILO_MAX_FRAMES+1];
  uint32_t newStarts[MILO_MAX_FRAMES+1];
  uint32_t frameNumber = 0;
 public:
  void reset() {
    frameNumber = 0;
    memset(starts, 0, sizeof(starts));
    for (int k=0;k<T;++k) {
      previous[k][0]=0;
      for (int j=1;j<=MILO_MAX_FRAMES;++j) previous[k][j]=1e9f;
    }
  }
  void features(const int16_t *pcm, float *out) {
    float mean=0;
    for (int i=0;i<320;++i) mean += pcm[i];
    mean /= 320;
    for (int i=0;i<512;++i) {
      real[i] = i<320 ? ((pcm[i]-mean)/32768.f)*MILO_WINDOW[i] : 0;
      imag[i] = 0;
    }
    for (int i=1,j=0;i<512;++i) {
      int bit=256;
      for (;j&bit;bit>>=1) j^=bit;
      j^=bit;
      if (i<j) { float v=real[i];real[i]=real[j];real[j]=v; }
    }
    for (int len=2;len<=512;len<<=1) {
      float angle=-6.283185307179586f/len;
      float wrStep=cosf(angle), wiStep=sinf(angle);
      for (int base=0;base<512;base+=len) {
        float wr=1,wi=0;
        for (int j=0;j<len/2;++j) {
          int a=base+j,b=a+len/2;
          float vr=real[b]*wr-imag[b]*wi, vi=real[b]*wi+imag[b]*wr;
          real[b]=real[a]-vr; imag[b]=imag[a]-vi;
          real[a]+=vr; imag[a]+=vi;
          float next=wr*wrStep-wi*wiStep;
          wi=wr*wiStep+wi*wrStep; wr=next;
        }
      }
    }
    float bands[20];
    for (int m=0;m<20;++m) {
      float total=0;
      for (int b=0;b<257;++b)
        total += MILO_MEL[m][b]*(real[b]*real[b]+imag[b]*imag[b])/512.f;
      bands[m]=logf(total>1e-12f ? total : 1e-12f);
    }
    float norm=0;
    for (int c=0;c<12;++c) {
      out[c]=0;
      for (int m=0;m<20;++m) out[c]+=MILO_DCT[c][m]*bands[m];
      norm+=out[c]*out[c];
    }
    norm=sqrtf(norm);
    for (int c=0;c<12;++c) out[c]/=norm>1e-9f ? norm : 1e-9f;
  }
  float feed(const int16_t *pcm, float rms) {
    uint32_t f=frameNumber++;
    if (!MILO_COUNT) return 1e9f;
    if (rms<MILO_ENERGY_FLOOR) {
      for (int k=0;k<MILO_COUNT;++k)
        for (int j=1;j<=MILO_LENGTHS[k];++j) previous[k][j]=1e9f;
      return 1e9f;
    }
    float x[12]; features(pcm,x);
    float best=1e9f;
    for (int k=0;k<MILO_COUNT;++k) {
      int n=MILO_LENGTHS[k]; current[0]=0;newStarts[0]=f;
      for (int j=1;j<=n;++j) {
        float cost=previous[k][j-1]; uint32_t start=j==1?f:starts[k][j-1];
        if (previous[k][j]<cost) { cost=previous[k][j];start=starts[k][j]; }
        if (current[j-1]<cost) { cost=current[j-1];start=newStarts[j-1]; }
        float distance=0;
        for (int c=0;c<12;++c) {
          float d=x[c]-MILO_TEMPLATES[k][(j-1)*12+c]/127.f;
          distance+=d*d;
        }
        current[j]=cost+distance; newStarts[j]=start;
      }
      uint32_t elapsed=f-newStarts[n]+1;
      float score=current[n]/(n+elapsed);
      if (elapsed>=uint32_t(n/2) && elapsed<=uint32_t(n*2) && score<best) best=score;
      memcpy(previous[k],current,(n+1)*sizeof(float));
      memcpy(starts[k],newStarts,(n+1)*sizeof(uint32_t));
    }
    return best;
  }
};
