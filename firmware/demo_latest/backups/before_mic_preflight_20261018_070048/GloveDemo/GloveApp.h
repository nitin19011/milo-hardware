#pragma once
#include <Wire.h>
#include <driver/gpio.h>

struct GloveRow { int64_t us;uint32_t seq;float imu[6];uint8_t fingers[3];uint8_t faults; };
static GloveRow gloveRows[GLOVE_SAMPLES];static uint16_t rowCount=0;
static Job handJob;
static const int FLEX_PINS[3]={35,34,39},MOTOR_PIN=25;
static const int BEND[3]={1369,1596,3435},RELEASE[3]={1353,1533,3420};
static const int FIST_MIN[3]={1676,1884,3480}; // Separate FULL-fist transmission gate, not model features.
static bool bent[3]={};static uint16_t flexRaw[3]={};
static bool imuConfigured=false,releaseRequired=true;
static uint32_t sampleSeq=0,generation=0;
static int64_t fistSince=0,nextSample=0,nextImuRetry=0,lastPrint=0;
static std::atomic<uint32_t> jobGeneration{0};
static std::atomic<bool> cueAllowed{false},cueStarted{false},recordStarted{false},recordEnded{false},endBuzzEnded{false};
static std::atomic<bool> ownSent{false},ownFailed{false};
static bool micReady=false,micSent=false,uploadQueued=false,captureAligned=false;
enum HandState { WAIT_OPEN,IDLE,HOLDING,RECORDING,ENDING,UPLOADING };
static std::atomic<int> handState{WAIT_OPEN};
static esp_timer_handle_t cueTimers[4]={};
struct HandEvent { uint8_t type;uint32_t generation;Job job; };
static QueueHandle_t handOut;
static char recentCaptures[8][33]={},feedbackIds[16][33]={},feedbackCaptures[16][33]={};static uint8_t captureSlot=0,feedbackSlot=0;
struct FeedbackPattern { uint8_t count=0,step=0;int64_t expiresMs=0,nextUs=0;bool running=false; };
static FeedbackPattern feedback;
static int64_t feedbackSuppressUntil=0;

static bool readReg(uint8_t reg,uint8_t *buffer,uint8_t n){Wire.beginTransmission(0x68);Wire.write(reg);if(Wire.endTransmission(false)!=0)return false;if(Wire.requestFrom(uint8_t(0x68),n,true)!=n){while(Wire.available())Wire.read();return false;}for(int i=0;i<n;i++)buffer[i]=Wire.read();return true;}
static bool writeReg(uint8_t reg,uint8_t v){Wire.beginTransmission(0x68);Wire.write(reg);Wire.write(v);return Wire.endTransmission()==0;}
static bool setupImu(){uint8_t who,r[2];return readReg(0x75,&who,1)&&who==0x68&&writeReg(0x6B,1)&&writeReg(0x6C,0)&&writeReg(0x1A,4)&&writeReg(0x19,4)&&writeReg(0x1B,0x18)&&writeReg(0x1C,0x18)&&readReg(0x1B,r,2)&&(r[0]&0x18)==0x18&&(r[1]&0x18)==0x18;}
static GloveRow sampleGlove(){
  GloveRow r{};r.us=esp_timer_get_time();r.seq=sampleSeq++;
  if(!imuConfigured&&r.us>=nextImuRetry){imuConfigured=setupImu();nextImuRetry=r.us+2000000;}
  uint8_t data[14];
  if(!imuConfigured||!readReg(0x3B,data,14)){r.faults|=8;imuConfigured=false;}
  else for(int i=0;i<6;i++){int source=i<3?i:i+1;int16_t raw=(uint16_t(data[source*2])<<8)|data[source*2+1];if(abs(int(raw))>=32700)r.faults|=16;r.imu[i]=i<3?raw*9.80665f/2048.0f:raw*0.01745329252f/16.4f;}
  for(int i=0;i<3;i++){analogRead(FLEX_PINS[i]);delayMicroseconds(200);uint32_t total=0;for(int k=0;k<8;k++)total+=analogRead(FLEX_PINS[i]);flexRaw[i]=total/8;
    if(flexRaw[i]<=20||flexRaw[i]>=4075)r.faults|=1<<i;
    else bent[i]=bent[i]?flexRaw[i]>RELEASE[i]:flexRaw[i]>=BEND[i];r.fingers[i]=bent[i];}
  return r;
}
static void motorTimer(void *arg){
  int phase=int(reinterpret_cast<intptr_t>(arg));
  if(phase==0){if(cueAllowed&&linkOnline){gpio_set_level(gpio_num_t(MOTOR_PIN),1);cueStarted=true;}}
  else if(phase==1){gpio_set_level(gpio_num_t(MOTOR_PIN),0);if(cueStarted)recordStarted=true;}
  else if(phase==2){if(recordStarted){recordEnded=true;gpio_set_level(gpio_num_t(MOTOR_PIN),1);}}
  else {gpio_set_level(gpio_num_t(MOTOR_PIN),0);if(recordStarted)endBuzzEnded=true;}
}
static void stopTimers(){cueAllowed=false;for(auto t:cueTimers)if(t)esp_timer_stop(t);gpio_set_level(gpio_num_t(MOTOR_PIN),0);}
static bool handEvent(uint8_t type){HandEvent e{type,jobGeneration.load(),handJob};return xQueueSend(handOut,&e,0)==pdTRUE;}
static void abortHand(const char *reason){Serial.printf("# Capture cancelled: %s\n",reason);stopTimers();handEvent(2);++droppedCaptures;releaseRequired=true;handState=WAIT_OPEN;deviceBusy=false;fistSince=0;}
static bool knownCapture(const char *id){if(handJob.id[0]&&!strcmp(id,handJob.id))return true;for(auto &v:recentCaptures)if(!strcmp(id,v))return true;return false;}
static void acceptFeedback(JsonDocument &doc){
  auto d=doc["data"];const char *id=d["feedback_id"]|"",*capture=d["capture_id"]|"",*reason=d["reason"]|"";
  if(doc["version"]!=1||strcmp(doc["source_id"]|"",ULTRA96_ID)||strcmp(d["target_source_id"]|"",HAND_ID)||strcmp(d["target_boot_id"]|"",bootId)||strcmp(d["haptic_profile_id"]|"","haptic-long-v1")||!validId(id)||!validId(capture)||!knownCapture(capture)||!clockValid())return;
  int64_t now=utcUs()/1000,expiry=d["expires_at_ms"]|int64_t(0),decision=doc["timestamp_ms"]|int64_t(0);
  if(expiry<=now||decision>now+100||now-decision>3000||feedback.count)return;
  for(int i=0;i<16;i++)if(!strcmp(id,feedbackIds[i])||!strcmp(capture,feedbackCaptures[i]))return;
  bool voice=!strcmp(reason,"VOICE_REJECTED")&&!strcmp(d["gesture_status"]|"","accepted")&&!strcmp(d["voice_status"]|"","rejected");
  bool gesture=!strcmp(reason,"GESTURE_REJECTED")&&!strcmp(d["gesture_status"]|"","rejected")&&!strcmp(d["voice_status"]|"","accepted");
  if(!voice&&!gesture)return;strcpy(feedbackIds[feedbackSlot],id);strcpy(feedbackCaptures[feedbackSlot],capture);feedbackSlot=(feedbackSlot+1)%16;
  feedback={uint8_t(voice?1:2),0,expiry,0,false};
}
static void handleHandControls(){Control c;while(xQueueReceive(controlQueue,&c,0)==pdTRUE){JsonDocument doc;if(deserializeJson(doc,c.body,c.size))continue;const char *type=doc["type"]|"";
  if(!strcmp(c.topic,topic("hand/feedback").c_str())&&!strcmp(type,"hand.feedback")){acceptFeedback(doc);continue;}
  auto d=doc["data"];if(strcmp(c.topic,topic("mic/results").c_str())||strcmp(doc["source_id"]|"",MIC_ID)||doc["version"]!=1||!sameJob(d,handJob)||strcmp(d["trigger_boot_id"]|"",bootId))continue;
  if(!strcmp(type,"demo.capture_ready")&&handState==HOLDING){
    int error=doc["clock_uncertainty_ms"]|1000000;
    if(int64_t(d["capture_start_ms"]|int64_t(0))==handJob.startMs&&error>=0&&error<=int(MAX_CLOCK_ERROR_MS))micReady=true;
  }else if(!strcmp(type,"demo.capture_sent"))micSent=true;
  else if(!strcmp(type,"demo.capture_failed")){if(handState==HOLDING&&!cueStarted)abortHand(d["reason"]|"mic failed");else{ownFailed=true;Serial.printf("# Mic failed: %s\n",d["reason"]|"unknown");}}
}}
static bool beginHand(const GloveRow &sample){
  portENTER_CRITICAL(&clockMux);if(clockUpdating||!linkOnline){portEXIT_CRITICAL(&clockMux);return false;}deviceBusy=true;auto c=currentClock;portEXIT_CRITICAL(&clockMux);
  handJob={};randomId(handJob.id);strcpy(handJob.handBoot,bootId);handJob.clock=c;handJob.clockError=clockErrorUs(c);
  handJob.startMs=(sample.us+c.offsetUs+3000000+999)/1000;handJob.startUs=handJob.startMs*1000-c.offsetUs;handJob.uploadMs=handJob.startMs+4000;handJob.deadlineMs=handJob.startMs+18000;
  jobGeneration=++generation;micReady=false;micSent=false;ownSent=false;ownFailed=false;uploadQueued=false;captureAligned=false;rowCount=0;
  cueAllowed=false;cueStarted=false;recordStarted=false;recordEnded=false;endBuzzEnded=false;
  int64_t targets[4]={handJob.startUs-1000000,handJob.startUs,handJob.startUs+3000000,handJob.startUs+4000000};
  for(int i=0;i<4;i++)if(esp_timer_start_once(cueTimers[i],max(int64_t(1),targets[i]-esp_timer_get_time()))!=ESP_OK){abortHand("timer allocation/start");return false;}
  handState=HOLDING;fistSince=sample.us;
  if(!handEvent(1)){abortHand("prepare queue full");return false;}
  Serial.printf("# Fist started. Capture %s: hold 2s, buzz 1s, record 3s, buzz 1s.\n",handJob.id);return true;
}
static void updateFeedback(int64_t now){
  if(!feedback.count)return;
  if(!feedback.running){if(handState!=WAIT_OPEN&&handState!=IDLE)return;if(utcUs()/1000>=feedback.expiresMs){feedback={};return;}feedback.running=true;feedback.step=0;feedback.nextUs=now;releaseRequired=true;}
  if(now<feedback.nextUs)return;
  if(feedback.step>=feedback.count*2-1){digitalWrite(MOTOR_PIN,LOW);feedback={};feedbackSuppressUntil=now+700000;return;}
  bool on=feedback.step%2==0;digitalWrite(MOTOR_PIN,on?HIGH:LOW);feedback.nextUs=now+(on?500000:250000);feedback.step++;
}
static void gloveSetup(){
  digitalWrite(MOTOR_PIN,LOW);pinMode(MOTOR_PIN,OUTPUT);runtimeSetup();Wire.begin(21,22);Wire.setClock(100000);Wire.setTimeOut(15);analogReadResolution(12);
  for(int pin:FLEX_PINS){pinMode(pin,INPUT);analogSetPinAttenuation(pin,ADC_11db);}
  imuConfigured=setupImu();handOut=xQueueCreate(4,sizeof(HandEvent));if(!handOut){Serial.println("# FATAL: hand queue");while(true)delay(1000);}
  for(int i=0;i<4;i++){esp_timer_create_args_t args{};args.callback=motorTimer;args.arg=reinterpret_cast<void*>(intptr_t(i));args.name="demoMotor";if(esp_timer_create(&args,&cueTimers[i])!=ESP_OK){Serial.println("# FATAL: motor timer");while(true)delay(1000);}}
  nextSample=esp_timer_get_time();Serial.println("# Open your hand first. No motor buzz until fist + mic readiness + valid clocks.");startNetwork();
}
static void gloveLoop(){
  handleHandControls();int64_t now=esp_timer_get_time();updateFeedback(now);
  if(cueStarted&&!captureAligned&&handState==RECORDING&&now>=handJob.startUs){nextSample=handJob.startUs;captureAligned=true;}
  if(now>=nextSample){
    nextSample+=20000;if(now-nextSample>20000)nextSample=now+20000;
    auto sample=sampleGlove();now=esp_timer_get_time();bool fist=!sample.faults;
    for(int i=0;i<3;i++)fist=fist&&bent[i]&&flexRaw[i]>=FIST_MIN[i];
    bool open=!sample.faults&&!bent[0]&&!bent[1]&&!bent[2];
    if(handState==WAIT_OPEN){if(open&&!feedback.count&&now>=feedbackSuppressUntil){releaseRequired=false;handState=IDLE;}}
    if(handState==IDLE&&fist&&!releaseRequired&&!feedback.count&&now>=feedbackSuppressUntil&&linkOnline&&clockValid()&&!clockUpdating)beginHand(sample);
    if(handState==HOLDING){
      if(!cueStarted&&(!fist||!linkOnline||!clockValid()||ownFailed)){abortHand("fist released, link/clock unavailable or prepare failed");}
      else {cueAllowed=micReady&&fist;if(cueStarted){handState=RECORDING;Serial.println("# Motor cue. Act/speak when it stops.");}}
    }
    if(cueStarted&&handState==RECORDING&&sample.us>=handJob.startUs&&sample.us<handJob.startUs+3000000){if(rowCount<GLOVE_SAMPLES)gloveRows[rowCount++]=sample;else ownFailed=true;}
    if(now-lastPrint>1000000&&handState<=IDLE){Serial.printf("# %s T=%u/%u I=%u/%u M=%u/%u clock=%s link=%s\n",captureState(),flexRaw[0],bent[0],flexRaw[1],bent[1],flexRaw[2],bent[2],clockValid()?"OK":"WAIT",linkOnline?"OK":"WAIT");lastPrint=now;}
  }
  now=esp_timer_get_time();
  if(handState==HOLDING&&!cueStarted&&now>handJob.startUs-995000)abortHand("mic not ready before cue deadline");
  if(handState==RECORDING&&recordEnded){handState=ENDING;Serial.printf("# Recording finished: %u/150 frames; ending buzz.\n",rowCount);}
  if(handState==ENDING&&endBuzzEnded&&!uploadQueued){uploadQueued=true;handState=UPLOADING;if(!handEvent(3))ownFailed=true;Serial.println("# Ending buzz finished. Uploading paired data.");}
  if(handState==UPLOADING&&((ownSent&&micSent)||ownFailed||utcUs()/1000>handJob.deadlineMs)){
    bool good=ownSent&&micSent&&!ownFailed;Serial.printf("# %s capture %s\n",good?"Both clips broker-acknowledged":"Capture failed/timed out",handJob.id);
    if(good){strcpy(recentCaptures[captureSlot],handJob.id);captureSlot=(captureSlot+1)%8;}else{++droppedCaptures;handEvent(2);}stopTimers();releaseRequired=true;handState=WAIT_OPEN;deviceBusy=false;
  }
  digitalWrite(LED_BUILTIN,linkOnline&&clockValid()?HIGH:((millis()/300)%2?HIGH:LOW));delay(1);
}
static const char *captureState(){switch(handState.load()){case WAIT_OPEN:return "wait_open";case IDLE:return "armed";case HOLDING:return "holding_fist";case RECORDING:return "cue_or_recording";case ENDING:return "ending_buzz";default:return "uploading";}}
static void deviceConnected(){}
static void deviceDisconnected(){if(handState==HOLDING&&!cueStarted)ownFailed=true;}
static void deviceOfflineTick(){}
static void fillMeta(JsonObject d){
  d["profile_id"]=HAND_PROFILE;d["sample_rate_hz"]=50;d["sample_count"]=150;d["duration_ms"]=3000;
  auto f=d["feature_names"].to<JsonArray>();for(const char *v:{"ax","ay","az","gx","gy","gz","thumb","index","middle"})f.add(v);
  d["finger_encoding"]="0=NOT_BENT,1=BENT";d["trigger"]="full_fist_2000ms";d["haptics"]["available"]=true;d["haptics"]["profile_id"]="haptic-long-v1";d["haptics"]["long_vibration_ms"]=500;d["haptics"]["inter_vibration_gap_ms"]=250;
  d["start_buzz_ms"]=1000;d["end_buzz_ms"]=1000;d["motor_gpio"]=25;d["capture_has_no_extra_settling_gap"]=true;d["accel_range_g"]=16;d["gyro_range_deg_s"]=2000;d["dlpf_hz"]=21;
}
static bool publishHandClip(const Job &j){
  bool valid=rowCount==150;uint32_t faults=0;int64_t first=rowCount?gloveRows[0].us:j.startUs;
  for(int i=0;i<rowCount;i++){faults|=gloveRows[i].faults;if(i&&(gloveRows[i].seq!=gloveRows[i-1].seq+1||gloveRows[i].us-gloveRows[i-1].us>30000||gloveRows[i].us<=gloveRows[i-1].us))valid=false;}
  valid=valid&&!faults&&clockValid();
  auto doc=envelope("hand.clip",4,first+j.clock.offsetUs,first);auto d=doc["data"].as<JsonObject>();jobData(d,j);d["trigger_time_ms"]=j.startMs-1000;d["profile_id"]=HAND_PROFILE;d["sample_rate_hz"]=50;d["sample_count"]=valid?rowCount:0;d["valid"]=valid;
  d["calibration_id"]="nitin-20261016-binary-60-30";d["mounting_id"]="nitin-sewn-glove";d["acquisition_revision"]="mpu16g-2000dps-21hz-flex8avg-demo1";d["imu_representation"]="SI units; gyro bias not subtracted";
  auto threshold=d["calibration"]["binary_thresholds"].to<JsonArray>();for(int i=0;i<3;i++){auto x=threshold.add<JsonObject>();x["bend"]=BEND[i];x["release"]=RELEASE[i];x["increases"]=true;}
  auto bias=d["calibration"]["reference_gyro_bias_rad_s"].to<JsonArray>();bias.add(-.027);bias.add(.018);bias.add(-.018);
  auto names=d["feature_names"].to<JsonArray>();for(const char *v:{"ax","ay","az","gx","gy","gz","thumb","index","middle"})names.add(v);
  auto errors=d["faults"].to<JsonArray>();if(!valid)errors.add("SENSOR_OR_TIMING_INVALID");d["sensor_fault_mask"]=faults;
  auto samples=d["samples"].to<JsonArray>(),offsets=d["sample_offsets_us"].to<JsonArray>();
  if(valid){d["first_sample_seq"]=gloveRows[0].seq;d["last_sample_seq"]=gloveRows[rowCount-1].seq;for(int i=0;i<rowCount;i++){auto row=samples.add<JsonArray>();for(float v:gloveRows[i].imu)row.add(v);for(uint8_t v:gloveRows[i].fingers)row.add(v);offsets.add(gloveRows[i].us-first);}}
  bool sent=sendJson("hand/clips",doc,false,j.startUs+18000000);return sent&&valid;
}
static void deviceNetworkTick(){HandEvent e;if(xQueueReceive(handOut,&e,0)!=pdTRUE)return;
  if(e.type==1){auto d=envelope("demo.capture_prepare",2);auto data=d["data"].as<JsonObject>();jobData(data,e.job);data["target_source_id"]=MIC_ID;data["expires_at_ms"]=e.job.deadlineMs;data["upload_not_before_ms"]=e.job.uploadMs;data["requested_profile_id"]=AUDIO_PROFILE;
    if(!sendJson("mic/capture",d)&&e.generation==jobGeneration)ownFailed=true;
  }else if(e.type==2){auto d=envelope("demo.capture_cancel",2);jobData(d["data"].as<JsonObject>(),e.job);sendJson("mic/capture",d);
  }else if(e.type==3){
    if(e.generation!=jobGeneration||utcUs()/1000>e.job.deadlineMs)return;
    if(rowCount!=150||ownFailed){ownFailed=true;return;}
    auto d=envelope("demo.capture_upload",2);jobData(d["data"].as<JsonObject>(),e.job);
    bool ok=sendJson("mic/capture",d,false,e.job.startUs+18000000)&&publishHandClip(e.job);
    if(e.generation==jobGeneration){ownSent=ok;if(!ok)ownFailed=true;}
  }
}
