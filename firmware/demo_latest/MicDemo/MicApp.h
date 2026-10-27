#pragma once
#include <driver/i2s_std.h>
#include <esp_heap_caps.h>
#include "DemoPcmStorage.h"

static const int MIC_BCLK=14,MIC_WS=17,MIC_SD=16;
static const uint32_t DMA_SAMPLES=160; // 10ms blocks; left 32-bit I2S, same gain as tested collar code.
static constexpr uint32_t PCM_BLOCK_SAMPLES=3200,PCM_BLOCK_COUNT=15;
static_assert(PCM_BLOCK_SAMPLES*PCM_BLOCK_COUNT==AUDIO_SAMPLES,"Exact 3-second audio storage");
static DemoPcmStorage<PCM_BLOCK_COUNT,PCM_BLOCK_SAMPLES> pcmStorage;
static uint8_t wavHeader[44];
static i2s_chan_handle_t rxChannel=nullptr;
enum MicPhase { MIC_IDLE,MIC_RESERVED,MIC_RECORDING,MIC_FROZEN,MIC_UPLOADING };
static std::atomic<int> micPhase{MIC_IDLE};
static portMUX_TYPE pcmMux=portMUX_INITIALIZER_UNLOCKED;
static bool pcmReady=false,audioUsingPcm=false;
static uint32_t lastPcmAllocationMs=0;
static bool pcmBuffersReady(){portENTER_CRITICAL(&pcmMux);bool v=pcmReady;portEXIT_CRITICAL(&pcmMux);return v;}
static bool acquirePcm(){portENTER_CRITICAL(&pcmMux);bool ok=pcmReady&&micPhase!=MIC_IDLE;if(ok)audioUsingPcm=true;portEXIT_CRITICAL(&pcmMux);return ok;}
static void finishPcmUse(){portENTER_CRITICAL(&pcmMux);audioUsingPcm=false;portEXIT_CRITICAL(&pcmMux);}
static bool allocatePcm(){
  if(pcmBuffersReady())return true;if(micPhase!=MIC_IDLE)return false;lastPcmAllocationMs=millis();
  Serial.printf("# PCM heap BEFORE: byte-accessible=%lu, word-accessible=%lu, largest byte block=%lu\n",
    (unsigned long)heap_caps_get_free_size(MALLOC_CAP_8BIT),(unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_32BIT),(unsigned long)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
  bool ok=pcmStorage.allocate([](size_t bytes)->void*{
    // Use word-only executable RAM first, preserving versatile DRAM for TLS/JSON.
    // PCM accesses are packed aligned uint32_t operations, never byte/halfword loads.
    return heap_caps_malloc_prefer(bytes,2,MALLOC_CAP_INTERNAL|MALLOC_CAP_32BIT|MALLOC_CAP_EXEC,MALLOC_CAP_INTERNAL|MALLOC_CAP_32BIT);
  },heap_caps_free);
  portENTER_CRITICAL(&pcmMux);pcmReady=ok;portEXIT_CRITICAL(&pcmMux);
  Serial.printf("# Audio storage %s AFTER TLS/MQTT: 96000 PCM bytes (packed 32-bit access); byte heap=%lu, word heap=%lu\n",ok?"ready":"allocation FAILED",(unsigned long)heap_caps_get_free_size(MALLOC_CAP_8BIT),(unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_32BIT));
  if(!ok)Serial.printf("# PCM allocation failed at block %u/%u; prior blocks released.\n",unsigned(pcmStorage.failureBlock+1),unsigned(PCM_BLOCK_COUNT));return ok;
}
static void releaseIdlePcm(){
  portENTER_CRITICAL(&pcmMux);bool release=pcmReady&&!audioUsingPcm&&micPhase==MIC_IDLE;if(release)pcmReady=false;portEXIT_CRITICAL(&pcmMux);
  if(release){pcmStorage.release(heap_caps_free);Serial.println("# Idle audio storage released for TLS reconnect.");}
}
static std::atomic<uint32_t> audioErrors{0};static uint32_t dmaSequence=0;
static portMUX_TYPE audioHealthMux=portMUX_INITIALIZER_UNLOCKED;static int64_t lastAudioUs=0;
struct DmaStamp { int64_t endUs;uint32_t sequence;uint32_t bytes; };
struct AudioCommand { uint8_t type;Job job; };
struct AudioEvent { uint8_t type;Job job;bool valid;uint32_t count;int64_t actualStartUs;int64_t jitterUs;char reason[40]; };
static QueueHandle_t stampQueue,audioCommands,audioEvents;
static Job micJob;static AudioEvent frozenAudio{};static bool wantUpload=false,lastSent=false;
struct CompletedMic { Job job;bool sent=false;char reason[40]={}; };
static CompletedMic micHistory[8];static uint8_t historySlot=0;

static bool IRAM_ATTR audioDma(i2s_chan_handle_t,i2s_event_data_t *event,void*){
  DmaStamp s{esp_timer_get_time(),dmaSequence++,uint32_t(event->size)};BaseType_t wake=pdFALSE;
  if(xQueueSendFromISR(stampQueue,&s,&wake)!=pdTRUE)audioErrors.fetch_add(1,std::memory_order_relaxed);
  return wake==pdTRUE;
}
static bool IRAM_ATTR audioOverflow(i2s_chan_handle_t,i2s_event_data_t*,void*){audioErrors.fetch_add(1,std::memory_order_relaxed);return false;}
static void little16(uint8_t *p,uint16_t v){p[0]=v;p[1]=v>>8;}
static void little32(uint8_t *p,uint32_t v){for(int i=0;i<4;i++)p[i]=v>>(i*8);}
static void makeWav(){memset(wavHeader,0,44);memcpy(wavHeader,"RIFF",4);little32(wavHeader+4,96036);memcpy(wavHeader+8,"WAVEfmt ",8);little32(wavHeader+16,16);little16(wavHeader+20,1);little16(wavHeader+22,1);little32(wavHeader+24,16000);little32(wavHeader+28,32000);little16(wavHeader+32,2);little16(wavHeader+34,16);memcpy(wavHeader+36,"data",4);little32(wavHeader+40,96000);}
static void postAudio(uint8_t type,const Job &j,bool valid,uint32_t count,int64_t start,int64_t jitter,const char *reason){AudioEvent e{type,j,valid,count,start,jitter,{}};strlcpy(e.reason,reason,sizeof(e.reason));if(xQueueSend(audioEvents,&e,0)!=pdTRUE)audioErrors++;}
static void audioTask(void*){
  int32_t raw[DMA_SAMPLES];Job active;bool recording=false,failed=false;uint32_t copied=0,baselineErrors=0;int64_t anchorUs=0,startIndex=0,maxJitter=0;uint32_t lastSeq=0;bool haveFrame=false;
  for(;;){
    DmaStamp stamp;if(xQueueReceive(stampQueue,&stamp,pdMS_TO_TICKS(100))!=pdTRUE){audioErrors++;if(recording){recording=false;micPhase=MIC_FROZEN;finishPcmUse();postAudio(2,active,false,copied,0,0,"I2S_TIMEOUT");}continue;}
    size_t bytes=0;esp_err_t err=i2s_channel_read(rxChannel,raw,sizeof(raw),&bytes,50);
    if(err!=ESP_OK||bytes!=sizeof(raw)||stamp.bytes!=sizeof(raw)){audioErrors++;if(recording)failed=true;continue;}
    int64_t firstIndex=int64_t(stamp.sequence)*DMA_SAMPLES;
    bool contiguous=!haveFrame||stamp.sequence==lastSeq+1;haveFrame=true;lastSeq=stamp.sequence;
    if(!contiguous){audioErrors++;if(recording)failed=true;}
    portENTER_CRITICAL(&audioHealthMux);lastAudioUs=stamp.endUs;portEXIT_CRITICAL(&audioHealthMux);
    AudioCommand cmd;
    while(xQueueReceive(audioCommands,&cmd,0)==pdTRUE){
      if(cmd.type==2){if(!strcmp(active.id,cmd.job.id)){recording=false;failed=false;finishPcmUse();}continue;}
      active=cmd.job;copied=0;failed=false;maxJitter=0;baselineErrors=audioErrors;
      if(!acquirePcm()){recording=false;if(micPhase!=MIC_IDLE){micPhase=MIC_FROZEN;postAudio(2,active,false,0,0,0,"AUDIO_STORAGE_NOT_READY");}continue;}
      // Anchor the ADC sample counter to a DMA-completion interrupt, not to delayed task wake-up.
      anchorUs=stamp.endUs-(firstIndex+DMA_SAMPLES)*1000000/AUDIO_HZ;
      startIndex=llround(double(active.startUs-anchorUs)*AUDIO_HZ/1000000.0);
      if(startIndex<firstIndex+DMA_SAMPLES){recording=false;micPhase=MIC_FROZEN;finishPcmUse();postAudio(2,active,false,0,0,0,"START_TOO_LATE");continue;}
      recording=true;postAudio(1,active,true,0,anchorUs+startIndex*1000000/AUDIO_HZ,0,"");
    }
    if(!recording)continue;
    int64_t residual=llabs(stamp.endUs-(anchorUs+(firstIndex+DMA_SAMPLES)*1000000/AUDIO_HZ));maxJitter=max(maxJitter,residual);
    if(residual>MAX_AUDIO_TIMELINE_ERROR_US||audioErrors.load()!=baselineErrors)failed=true;
    for(int i=0;i<int(DMA_SAMPLES);i++){
      int64_t index=firstIndex+i;if(index<startIndex||index>=startIndex+AUDIO_SAMPLES)continue;
      if(uint32_t(index-startIndex)!=copied){failed=true;continue;}
      int32_t value=(raw[i]>>16)*4;pcmStorage.setSample(copied,int16_t(constrain(value,-32768,32767)));copied++;micPhase=MIC_RECORDING;
    }
    if(firstIndex+DMA_SAMPLES>=startIndex+AUDIO_SAMPLES){
      bool valid=!failed&&copied==AUDIO_SAMPLES;recording=false;micPhase=MIC_FROZEN;finishPcmUse();
      postAudio(2,active,valid,copied,anchorUs+startIndex*1000000/AUDIO_HZ,maxJitter,valid?"":"AUDIO_GAP_OR_TIMING_INVALID");
    }
  }
}
static bool audioHealthy(){portENTER_CRITICAL(&audioHealthMux);int64_t last=lastAudioUs;portEXIT_CRITICAL(&audioHealthMux);return last&&esp_timer_get_time()-last<100000;}
static void micResult(const char *type,const Job &job,const char *reason=""){
  auto doc=envelope(type,3);auto d=doc["data"].as<JsonObject>();jobData(d,job);d["target_source_id"]=HAND_ID;d["reason"]=reason;d["profile_id"]=AUDIO_PROFILE;
  sendJson("mic/results",doc);
}
static void rememberMic(bool sent,const char *reason){auto &c=micHistory[historySlot];c.job=micJob;c.sent=sent;strlcpy(c.reason,reason,sizeof(c.reason));historySlot=(historySlot+1)%8;}
static void cancelAudio(){AudioCommand cmd{2,micJob};xQueueSend(audioCommands,&cmd,0);micPhase=MIC_IDLE;deviceBusy=false;wantUpload=false;}
static bool publishWav(){
  auto &e=frozenAudio;auto doc=envelope("mic.clip",4,e.actualStartUs+micJob.clock.offsetUs,e.actualStartUs);auto d=doc["data"].as<JsonObject>();jobData(d,micJob);
  d["trigger_time_ms"]=micJob.startMs-1000;d["profile_id"]=AUDIO_PROFILE;d["encoding"]="wav_pcm_s16le";d["sample_rate_hz"]=16000;d["channels"]=1;d["bits_per_sample"]=16;d["sample_count"]=48000;d["wav_byte_length"]=96044;d["pcm_byte_length"]=96000;
  d["actual_start_ms"]=(e.actualStartUs+micJob.clock.offsetUs)/1000;d["actual_end_ms"]=(e.actualStartUs+micJob.clock.offsetUs+3000000)/1000;d["alignment_error_ms"]=(e.actualStartUs-micJob.startUs)/1000.0;d["dma_timeline_jitter_us"]=e.jitterUs;d["estimated_timing_uncertainty_ms"]=(micJob.clockError+e.jitterUs+2000)/1000.0;d["valid"]=true;d["faults"].to<JsonArray>();
  if(doc.overflowed())return false;String json;if(!json.reserve(measureJson(doc)+1))return false;serializeJson(doc,json);uint32_t length=json.length();uint8_t prefix[8]={'M','L','W','1',uint8_t(length>>24),uint8_t(length>>16),uint8_t(length>>8),uint8_t(length)};
  DemoMqtt::Part parts[4]={{prefix,8},{reinterpret_cast<const uint8_t*>(json.c_str()),json.length()},{wavHeader,44},
    {nullptr,pcmStorage.byteSize,decltype(pcmStorage)::readBytes,&pcmStorage}};
  return mqtt.publishParts(topic("mic/clips").c_str(),parts,4,false,micJob.startUs+18000000);
}
static void deviceNetworkTick(){
  if(micPhase==MIC_IDLE&&!pcmBuffersReady()&&uint32_t(millis()-lastPcmAllocationMs)>5000)allocatePcm();
  AudioEvent event;
  while(xQueueReceive(audioEvents,&event,0)==pdTRUE){
    if(strcmp(event.job.id,micJob.id)||micPhase==MIC_IDLE)continue;
    if(event.type==1){micResult("demo.capture_ready",micJob);Serial.printf("# Scheduled mic %s at %lld ms UTC\n",micJob.id,(long long)micJob.startMs);}
    else{frozenAudio=event;if(!event.valid){micResult("demo.capture_failed",micJob,event.reason);rememberMic(false,event.reason);++droppedCaptures;cancelAudio();}else Serial.printf("# WAV frozen: %lu samples, waiting for ending buzz/upload gate.\n",(unsigned long)event.count);}
  }
  Control c;
  while(xQueueReceive(controlQueue,&c,0)==pdTRUE){
    JsonDocument doc;if(deserializeJson(doc,c.body,c.size)||strcmp(c.topic,topic("mic/capture").c_str())||doc["version"]!=1||strcmp(doc["source_id"]|"",HAND_ID))continue;
    auto d=doc["data"];const char *type=doc["type"]|"",*id=d["capture_id"]|"",*handBoot=doc["boot_id"]|"";
    if(!validId(id)||!validId(handBoot))continue;
    if(!strcmp(type,"demo.capture_prepare")){
      bool duplicate=false;for(auto &h:micHistory)if(!strcmp(id,h.job.id)){micResult(h.sent?"demo.capture_sent":"demo.capture_failed",h.job,h.reason);duplicate=true;break;}if(duplicate)continue;
      if(micPhase!=MIC_IDLE){if(sameJob(d,micJob)&&!strcmp(handBoot,micJob.handBoot)&&int64_t(d["capture_start_ms"]|int64_t(0))==micJob.startMs)micResult("demo.capture_ready",micJob);else{Job other{};strcpy(other.id,id);strcpy(other.handBoot,handBoot);micResult("demo.capture_failed",other,"BUSY_OR_CAPTURE_ID_CONFLICT");}continue;}
      Job proposed;
      if(!readJob(doc,proposed)||strcmp(d["requested_profile_id"]|"",AUDIO_PROFILE)||!audioHealthy()||!pcmBuffersReady()){
        strcpy(proposed.id,id);strcpy(proposed.handBoot,handBoot);micResult("demo.capture_failed",proposed,!clockValid()?"CLOCK_UNSYNCED":(!pcmBuffersReady()?"AUDIO_STORAGE_NOT_READY":"INVALID_REQUEST_OR_I2S_NOT_READY"));continue;}
      portENTER_CRITICAL(&clockMux);if(clockUpdating){portEXIT_CRITICAL(&clockMux);micResult("demo.capture_failed",proposed,"CLOCK_UPDATING");continue;}deviceBusy=true;portEXIT_CRITICAL(&clockMux);
      micJob=proposed;micPhase=MIC_RESERVED;wantUpload=false;lastSent=false;frozenAudio={};AudioCommand cmd{1,micJob};
      if(xQueueSend(audioCommands,&cmd,0)!=pdTRUE){micResult("demo.capture_failed",micJob,"AUDIO_COMMAND_QUEUE_FULL");cancelAudio();}
    }else if(sameJob(d,micJob)&&!strcmp(handBoot,micJob.handBoot)){
      if(!strcmp(type,"demo.capture_cancel")){if(micPhase!=MIC_IDLE){micResult("demo.capture_failed",micJob,"CANCELLED");rememberMic(false,"CANCELLED");cancelAudio();}}
      else if(!strcmp(type,"demo.capture_upload")){if(lastSent)micResult("demo.capture_sent",micJob);else if(micPhase!=MIC_IDLE)wantUpload=true;}
    }
  }
  if(micPhase!=MIC_IDLE&&utcUs()/1000>micJob.deadlineMs){micResult("demo.capture_failed",micJob,"CAPTURE_EXPIRED");rememberMic(false,"CAPTURE_EXPIRED");++droppedCaptures;cancelAudio();}
  if(micPhase==MIC_FROZEN&&frozenAudio.valid&&wantUpload&&utcUs()/1000>=micJob.uploadMs){
    micPhase=MIC_UPLOADING;bool ok=publishWav();lastSent=ok;
    if(ok){rememberMic(true,"");micResult("demo.capture_sent",micJob);Serial.printf("# WAV broker-acknowledged: %s, 96044 WAV bytes\n",micJob.id);micPhase=MIC_IDLE;deviceBusy=false;wantUpload=false;}
    else{micPhase=MIC_FROZEN;Serial.println("# WAV upload interrupted; frozen clip retained until deadline/reconnect.");}
  }
}
static const char *captureState(){switch(micPhase.load()){case MIC_IDLE:return !pcmBuffersReady()?"audio_memory_wait":(audioHealthy()?"ready":"i2s_not_ready");case MIC_RESERVED:return "scheduled";case MIC_RECORDING:return "recording";case MIC_FROZEN:return "frozen_wait_upload";default:return "uploading";}}
static void deviceConnected(){if(micPhase==MIC_IDLE)allocatePcm();if(lastSent&&micJob.id[0]&&utcUs()/1000<micJob.deadlineMs)micResult("demo.capture_sent",micJob);}
static void deviceDisconnected(){releaseIdlePcm();} // Active/frozen clips remain owned until their original deadline.
static void deviceOfflineTick(){if(micPhase!=MIC_IDLE&&esp_timer_get_time()>micJob.startUs+18000000){rememberMic(false,"OFFLINE_EXPIRED");++droppedCaptures;cancelAudio();Serial.println("# Offline capture expired; local buffers released.");}releaseIdlePcm();}
static void fillDeviceHealth(JsonObject h){h["audio_ready"]=audioHealthy();h["audio_buffers_ready"]=pcmBuffersReady();h["largest_free_block"]=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);h["free_byte_heap"]=heap_caps_get_free_size(MALLOC_CAP_8BIT);h["free_word_heap"]=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_32BIT);h["pcm_storage"]="packed32_96000_bytes";h["audio_errors_total"]=audioErrors.load();h["capture_mode"]="demo_synchronized";}
static void fillMeta(JsonObject d){d["profile_id"]=AUDIO_PROFILE;d["encoding"]="wav_pcm_s16le";d["sample_rate_hz"]=16000;d["channels"]=1;d["bits_per_sample"]=16;d["sample_count"]=48000;d["duration_ms"]=3000;d["wav_byte_length"]=96044;d["envelope_magic"]="MLW1";d["concurrent_captures"]=1;d["ready"]=audioHealthy()&&pcmBuffersReady()&&micPhase==MIC_IDLE;d["capture_state"]=captureState();d["audio_errors_total"]=audioErrors.load();d["scheduling"]="future UTC start; DMA sample-index mapping";}
static void micSetup(){
  runtimeSetup();makeWav();stampQueue=xQueueCreate(8,sizeof(DmaStamp));audioCommands=xQueueCreate(4,sizeof(AudioCommand));audioEvents=xQueueCreate(4,sizeof(AudioEvent));
  if(!stampQueue||!audioCommands||!audioEvents){Serial.println("# FATAL: audio queue allocation");while(true)delay(1000);}
  // Small heap blocks avoid the ESP32 static-DRAM limit and one large contiguous allocation.
  // These are local storage pieces, NOT separate MQTT messages.
  Serial.println("# PCM allocation deferred: preserving 96000 bytes for the TLS handshake.");
  i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);channel.dma_desc_num=6;channel.dma_frame_num=DMA_SAMPLES;
  i2s_std_config_t standard{};standard.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_HZ);standard.slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,I2S_SLOT_MODE_MONO);standard.slot_cfg.slot_mask=I2S_STD_SLOT_LEFT;
  standard.gpio_cfg.mclk=I2S_GPIO_UNUSED;standard.gpio_cfg.bclk=gpio_num_t(MIC_BCLK);standard.gpio_cfg.ws=gpio_num_t(MIC_WS);standard.gpio_cfg.dout=I2S_GPIO_UNUSED;standard.gpio_cfg.din=gpio_num_t(MIC_SD);
  i2s_event_callbacks_t callbacks{};callbacks.on_recv=audioDma;callbacks.on_recv_q_ovf=audioOverflow;
  if(i2s_new_channel(&channel,nullptr,&rxChannel)!=ESP_OK||i2s_channel_init_std_mode(rxChannel,&standard)!=ESP_OK||i2s_channel_register_event_callback(rxChannel,&callbacks,nullptr)!=ESP_OK||i2s_channel_enable(rxChannel)!=ESP_OK){Serial.println("# FATAL: I2S setup. INMP441 BCLK14 WS17 SD16 L/R=GND.");while(true)delay(1000);}
  if(xTaskCreatePinnedToCore(audioTask,"demoAudio",6000,nullptr,3,nullptr,1)!=pdPASS){Serial.println("# FATAL: audio task allocation");while(true)delay(1000);}
  Serial.println("# Mic captures locally; no waveform upload until glove ends recording and final buzz.");startNetwork();
}
static void micLoop(){digitalWrite(LED_BUILTIN,linkOnline&&clockValid()?HIGH:((millis()/300)%2?HIGH:LOW));delay(20);}
