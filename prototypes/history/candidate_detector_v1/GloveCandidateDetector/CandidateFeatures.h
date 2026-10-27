#pragma once
#include <cmath>
#include <algorithm>

// Matches training/features.py. Means and moments accumulate in double;
// quantize to 1e-4 so training and embedded arithmetic share a stable grid.
static inline float miloQuantize(double x) { return float(std::floor(x*10000.0+0.5)/10000.0); }
static inline void miloFeatures(const float window[40][12], float out[45]) {
  for(int c=0;c<6;c++) {
    double sum=0,squares=0,diff=0,low=window[0][c],high=low;
    for(int i=0;i<40;i++) {
      double x=window[i][c];sum+=x;squares+=x*x;
      low=std::min(low,x);high=std::max(high,x);
      if(i)diff+=std::fabs(x-window[i-1][c]);
    }
    double mean=sum/40.0;
    out[c]=miloQuantize(mean);
    out[6+c]=miloQuantize(std::sqrt(std::max(0.0,squares/40.0-mean*mean)));
    out[12+c]=miloQuantize(high-low);out[18+c]=miloQuantize(diff/39.0);
  }
  double gyroSum=0,gyroSquares=0,gyroMax=0,accSum=0,accSquares=0;
  double accLow=0,accHigh=0,accDiff=0,previousAcc=0;
  for(int i=0;i<40;i++) {
    double gx=window[i][3],gy=window[i][4],gz=window[i][5];
    double ax=window[i][0],ay=window[i][1],az=window[i][2];
    double g=std::sqrt(gx*gx+gy*gy+gz*gz),a=std::sqrt(ax*ax+ay*ay+az*az);
    gyroSum+=g;gyroSquares+=g*g;gyroMax=std::max(gyroMax,g);
    accSum+=a;accSquares+=a*a;
    if(!i)accLow=accHigh=a;
    else {accLow=std::min(accLow,a);accHigh=std::max(accHigh,a);accDiff+=std::fabs(a-previousAcc);}
    previousAcc=a;
  }
  double gm=gyroSum/40.0,am=accSum/40.0;
  out[24]=miloQuantize(gm);out[25]=miloQuantize(std::sqrt(std::max(0.0,gyroSquares/40.0-gm*gm)));out[26]=miloQuantize(gyroMax);
  out[27]=miloQuantize(std::sqrt(std::max(0.0,accSquares/40.0-am*am)));out[28]=miloQuantize(accHigh-accLow);out[29]=miloQuantize(accDiff/39.0);
  static const double spans[3]={436.5,613.5,120.5};
  for(int c=0;c<3;c++) {
    double sum=0,transitions=0,low=window[0][9+c],high=low,diff=0;
    for(int i=0;i<40;i++) {
      sum+=window[i][6+c];double x=window[i][9+c];low=std::min(low,x);high=std::max(high,x);
      if(i){transitions+=window[i][6+c]!=window[i-1][6+c];diff+=std::fabs(x-window[i-1][9+c]);}
    }
    out[30+c]=miloQuantize(window[39][6+c]);out[33+c]=miloQuantize(sum/40.0);out[36+c]=miloQuantize(transitions);
    out[39+c]=miloQuantize((high-low)/spans[c]);out[42+c]=miloQuantize(diff/39.0/spans[c]);
  }
}
