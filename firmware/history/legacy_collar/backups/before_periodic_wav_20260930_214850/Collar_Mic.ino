#include <Arduino.h>
#include "ESP_I2S.h"
#include <WiFi.h>

#include <esp_timer.h>

const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";
const char MQTT_BROKER_IP[] = "172.20.10.2";
const uint16_t MQTT_BROKER_PORT = 1883;
const uint32_t MQTT_RETRY_MS = 5000;
const char MIC_TOPIC[] = "sensor/collar/microphone";
const char CONNECTION_TOPIC[] = "status/collar/connection";
const char CONNECTION_ONLINE_PAYLOAD[] =
  "{\"schema_version\":1,\"type\":\"connection_status\",\"source_id\":\"collar\",\"state\":\"ONLINE\"}";
const char CONNECTION_OFFLINE_PAYLOAD[] =
  "{\"schema_version\":1,\"type\":\"connection_status\",\"source_id\":\"collar\",\"state\":\"OFFLINE\"}";

// INMP441 VDD->3V3; GND AND L/R->GND. These are GPIO numbers.
const int MIC_BCLK=14, MIC_WS=17, MIC_SD=16;
const uint32_t MIC_RATE=16000, MIC_PUBLISH_MS=200;

/* Third-party attribution and license (also in THIRD_PARTY.md):
# CollarMqtt: local PubSubClient derivative

Source: the installed Nick O'Leary PubSubClient library (https://github.com/knolleary/pubsubclient).
Only the class/file names, outgoing buildHeader length type (uint16_t to uint32_t),
and beginPublish topic/payload bounds were changed. Ordinary publish() and incoming
packet handling retain their small-buffer limits. WAVs MUST use beginPublish/write/endPublish.
No globally installed library is modified. Keep this notice with distributed code.

Copyright (c) 2008-2020 Nicholas O'Leary

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

*/

// BEGIN EMBEDDED CollarMqtt.h
// Local PubSubClient derivative: outgoing beginPublish uses a 32-bit Remaining Length.
// All other APIs retain upstream limits. Large INCOMING messages are not supported.
// Renamed to avoid changing the installed library used by the glove. See THIRD_PARTY.md.
/*
 CollarMqtt.h - A simple client for MQTT.
  Nick O'Leary
  http://knolleary.net
*/

#ifndef CollarMqtt_h
#define CollarMqtt_h

#include <Arduino.h>
#include "IPAddress.h"
#include "Client.h"
#include "Stream.h"

#define MQTT_VERSION_3_1      3
#define MQTT_VERSION_3_1_1    4

// MQTT_VERSION : Pick the version
//#define MQTT_VERSION MQTT_VERSION_3_1
#ifndef MQTT_VERSION
#define MQTT_VERSION MQTT_VERSION_3_1_1
#endif

// MQTT_MAX_PACKET_SIZE : Maximum packet size. Override with setBufferSize().
#ifndef MQTT_MAX_PACKET_SIZE
#define MQTT_MAX_PACKET_SIZE 256
#endif

// MQTT_KEEPALIVE : keepAlive interval in Seconds. Override with setKeepAlive()
#ifndef MQTT_KEEPALIVE
#define MQTT_KEEPALIVE 15
#endif

// MQTT_SOCKET_TIMEOUT: socket timeout interval in Seconds. Override with setSocketTimeout()
#ifndef MQTT_SOCKET_TIMEOUT
#define MQTT_SOCKET_TIMEOUT 15
#endif

// MQTT_MAX_TRANSFER_SIZE : limit how much data is passed to the network client
//  in each write call. Needed for the Arduino Wifi Shield. Leave undefined to
//  pass the entire MQTT packet in each write call.
//#define MQTT_MAX_TRANSFER_SIZE 80

// Possible values for client.state()
#define MQTT_CONNECTION_TIMEOUT     -4
#define MQTT_CONNECTION_LOST        -3
#define MQTT_CONNECT_FAILED         -2
#define MQTT_DISCONNECTED           -1
#define MQTT_CONNECTED               0
#define MQTT_CONNECT_BAD_PROTOCOL    1
#define MQTT_CONNECT_BAD_CLIENT_ID   2
#define MQTT_CONNECT_UNAVAILABLE     3
#define MQTT_CONNECT_BAD_CREDENTIALS 4
#define MQTT_CONNECT_UNAUTHORIZED    5

#define MQTTCONNECT     1 << 4  // Client request to connect to Server
#define MQTTCONNACK     2 << 4  // Connect Acknowledgment
#define MQTTPUBLISH     3 << 4  // Publish message
#define MQTTPUBACK      4 << 4  // Publish Acknowledgment
#define MQTTPUBREC      5 << 4  // Publish Received (assured delivery part 1)
#define MQTTPUBREL      6 << 4  // Publish Release (assured delivery part 2)
#define MQTTPUBCOMP     7 << 4  // Publish Complete (assured delivery part 3)
#define MQTTSUBSCRIBE   8 << 4  // Client Subscribe request
#define MQTTSUBACK      9 << 4  // Subscribe Acknowledgment
#define MQTTUNSUBSCRIBE 10 << 4 // Client Unsubscribe request
#define MQTTUNSUBACK    11 << 4 // Unsubscribe Acknowledgment
#define MQTTPINGREQ     12 << 4 // PING Request
#define MQTTPINGRESP    13 << 4 // PING Response
#define MQTTDISCONNECT  14 << 4 // Client is Disconnecting
#define MQTTReserved    15 << 4 // Reserved

#define MQTTQOS0        (0 << 1)
#define MQTTQOS1        (1 << 1)
#define MQTTQOS2        (2 << 1)

// Maximum size of fixed header and variable length size header
#define MQTT_MAX_HEADER_SIZE 5

#if defined(ESP8266) || defined(ESP32)
#include <functional>
#define MQTT_CALLBACK_SIGNATURE std::function<void(char*, uint8_t*, unsigned int)> callback
#else
#define MQTT_CALLBACK_SIGNATURE void (*callback)(char*, uint8_t*, unsigned int)
#endif

#define CHECK_STRING_LENGTH(l,s) if (l+2+strnlen(s, this->bufferSize) > this->bufferSize) {_client->stop();return false;}

class CollarMqtt : public Print {
private:
   Client* _client;
   uint8_t* buffer;
   uint16_t bufferSize;
   uint16_t keepAlive;
   uint16_t socketTimeout;
   uint16_t nextMsgId;
   unsigned long lastOutActivity;
   unsigned long lastInActivity;
   bool pingOutstanding;
   MQTT_CALLBACK_SIGNATURE;
   uint32_t readPacket(uint8_t*);
   boolean readByte(uint8_t * result);
   boolean readByte(uint8_t * result, uint16_t * index);
   boolean write(uint8_t header, uint8_t* buf, uint16_t length);
   uint16_t writeString(const char* string, uint8_t* buf, uint16_t pos);
   // Build up the header ready to send
   // Returns the size of the header
   // Note: the header is built at the end of the first MQTT_MAX_HEADER_SIZE bytes, so will start
   //       (MQTT_MAX_HEADER_SIZE - <returned size>) bytes into the buffer
   size_t buildHeader(uint8_t header, uint8_t* buf, uint32_t length);
   IPAddress ip;
   const char* domain;
   uint16_t port;
   Stream* stream;
   int _state;
public:
   CollarMqtt();
   CollarMqtt(Client& client);
   CollarMqtt(IPAddress, uint16_t, Client& client);
   CollarMqtt(IPAddress, uint16_t, Client& client, Stream&);
   CollarMqtt(IPAddress, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client);
   CollarMqtt(IPAddress, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client, Stream&);
   CollarMqtt(uint8_t *, uint16_t, Client& client);
   CollarMqtt(uint8_t *, uint16_t, Client& client, Stream&);
   CollarMqtt(uint8_t *, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client);
   CollarMqtt(uint8_t *, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client, Stream&);
   CollarMqtt(const char*, uint16_t, Client& client);
   CollarMqtt(const char*, uint16_t, Client& client, Stream&);
   CollarMqtt(const char*, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client);
   CollarMqtt(const char*, uint16_t, MQTT_CALLBACK_SIGNATURE,Client& client, Stream&);

   ~CollarMqtt();

   CollarMqtt& setServer(IPAddress ip, uint16_t port);
   CollarMqtt& setServer(uint8_t * ip, uint16_t port);
   CollarMqtt& setServer(const char * domain, uint16_t port);
   CollarMqtt& setCallback(MQTT_CALLBACK_SIGNATURE);
   CollarMqtt& setClient(Client& client);
   CollarMqtt& setStream(Stream& stream);
   CollarMqtt& setKeepAlive(uint16_t keepAlive);
   CollarMqtt& setSocketTimeout(uint16_t timeout);

   boolean setBufferSize(uint16_t size);
   uint16_t getBufferSize();

   boolean connect(const char* id);
   boolean connect(const char* id, const char* user, const char* pass);
   boolean connect(const char* id, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage);
   boolean connect(const char* id, const char* user, const char* pass, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage);
   boolean connect(const char* id, const char* user, const char* pass, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage, boolean cleanSession);
   void disconnect();
   boolean publish(const char* topic, const char* payload);
   boolean publish(const char* topic, const char* payload, boolean retained);
   boolean publish(const char* topic, const uint8_t * payload, unsigned int plength);
   boolean publish(const char* topic, const uint8_t * payload, unsigned int plength, boolean retained);
   boolean publish_P(const char* topic, const char* payload, boolean retained);
   boolean publish_P(const char* topic, const uint8_t * payload, unsigned int plength, boolean retained);
   // Start to publish a message.
   // This API:
   //   beginPublish(...)
   //   one or more calls to write(...)
   //   endPublish()
   // Allows for arbitrarily large payloads to be sent without them having to be copied into
   // a new buffer and held in memory at one time
   // Returns 1 if the message was started successfully, 0 if there was an error
   boolean beginPublish(const char* topic, unsigned int plength, boolean retained);
   // Finish off this publish message (started with beginPublish)
   // Returns 1 if the packet was sent successfully, 0 if there was an error
   int endPublish();
   // Write a single byte of payload (only to be used with beginPublish/endPublish)
   virtual size_t write(uint8_t);
   // Write size bytes from buffer into the payload (only to be used with beginPublish/endPublish)
   // Returns the number of bytes written
   virtual size_t write(const uint8_t *buffer, size_t size);
   boolean subscribe(const char* topic);
   boolean subscribe(const char* topic, uint8_t qos);
   boolean unsubscribe(const char* topic);
   boolean loop();
   boolean connected();
   int state();

};


#endif
// END EMBEDDED CollarMqtt.h

// BEGIN EMBEDDED CollarMqtt.cpp
// Local PubSubClient derivative: outgoing beginPublish uses a 32-bit Remaining Length.
// All other APIs retain upstream limits. Large INCOMING messages are not supported.
// Renamed to avoid changing the installed library used by the glove. See THIRD_PARTY.md.
/*

  CollarMqtt.cpp - A simple client for MQTT.
  Nick O'Leary
  http://knolleary.net
*/


#include "Arduino.h"

CollarMqtt::CollarMqtt() {
    this->_state = MQTT_DISCONNECTED;
    this->_client = NULL;
    this->stream = NULL;
    setCallback(NULL);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}

CollarMqtt::CollarMqtt(Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}

CollarMqtt::CollarMqtt(IPAddress addr, uint16_t port, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(addr, port);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(IPAddress addr, uint16_t port, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(addr,port);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(IPAddress addr, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(addr, port);
    setCallback(callback);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(IPAddress addr, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(addr,port);
    setCallback(callback);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}

CollarMqtt::CollarMqtt(uint8_t *ip, uint16_t port, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(ip, port);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(uint8_t *ip, uint16_t port, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(ip,port);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(uint8_t *ip, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(ip, port);
    setCallback(callback);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(uint8_t *ip, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(ip,port);
    setCallback(callback);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}

CollarMqtt::CollarMqtt(const char* domain, uint16_t port, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(domain,port);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(const char* domain, uint16_t port, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(domain,port);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(const char* domain, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client) {
    this->_state = MQTT_DISCONNECTED;
    setServer(domain,port);
    setCallback(callback);
    setClient(client);
    this->stream = NULL;
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}
CollarMqtt::CollarMqtt(const char* domain, uint16_t port, MQTT_CALLBACK_SIGNATURE, Client& client, Stream& stream) {
    this->_state = MQTT_DISCONNECTED;
    setServer(domain,port);
    setCallback(callback);
    setClient(client);
    setStream(stream);
    this->bufferSize = 0;
    setBufferSize(MQTT_MAX_PACKET_SIZE);
    setKeepAlive(MQTT_KEEPALIVE);
    setSocketTimeout(MQTT_SOCKET_TIMEOUT);
}

CollarMqtt::~CollarMqtt() {
  free(this->buffer);
}

boolean CollarMqtt::connect(const char *id) {
    return connect(id,NULL,NULL,0,0,0,0,1);
}

boolean CollarMqtt::connect(const char *id, const char *user, const char *pass) {
    return connect(id,user,pass,0,0,0,0,1);
}

boolean CollarMqtt::connect(const char *id, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage) {
    return connect(id,NULL,NULL,willTopic,willQos,willRetain,willMessage,1);
}

boolean CollarMqtt::connect(const char *id, const char *user, const char *pass, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage) {
    return connect(id,user,pass,willTopic,willQos,willRetain,willMessage,1);
}

boolean CollarMqtt::connect(const char *id, const char *user, const char *pass, const char* willTopic, uint8_t willQos, boolean willRetain, const char* willMessage, boolean cleanSession) {
    if (!connected()) {
        int result = 0;


        if(_client->connected()) {
            result = 1;
        } else {
            if (domain != NULL) {
                result = _client->connect(this->domain, this->port);
            } else {
                result = _client->connect(this->ip, this->port);
            }
        }

        if (result == 1) {
            nextMsgId = 1;
            // Leave room in the buffer for header and variable length field
            uint16_t length = MQTT_MAX_HEADER_SIZE;
            unsigned int j;

#if MQTT_VERSION == MQTT_VERSION_3_1
            uint8_t d[9] = {0x00,0x06,'M','Q','I','s','d','p', MQTT_VERSION};
#define MQTT_HEADER_VERSION_LENGTH 9
#elif MQTT_VERSION == MQTT_VERSION_3_1_1
            uint8_t d[7] = {0x00,0x04,'M','Q','T','T',MQTT_VERSION};
#define MQTT_HEADER_VERSION_LENGTH 7
#endif
            for (j = 0;j<MQTT_HEADER_VERSION_LENGTH;j++) {
                this->buffer[length++] = d[j];
            }

            uint8_t v;
            if (willTopic) {
                v = 0x04|(willQos<<3)|(willRetain<<5);
            } else {
                v = 0x00;
            }
            if (cleanSession) {
                v = v|0x02;
            }

            if(user != NULL) {
                v = v|0x80;

                if(pass != NULL) {
                    v = v|(0x80>>1);
                }
            }
            this->buffer[length++] = v;

            this->buffer[length++] = ((this->keepAlive) >> 8);
            this->buffer[length++] = ((this->keepAlive) & 0xFF);

            CHECK_STRING_LENGTH(length,id)
            length = writeString(id,this->buffer,length);
            if (willTopic) {
                CHECK_STRING_LENGTH(length,willTopic)
                length = writeString(willTopic,this->buffer,length);
                CHECK_STRING_LENGTH(length,willMessage)
                length = writeString(willMessage,this->buffer,length);
            }

            if(user != NULL) {
                CHECK_STRING_LENGTH(length,user)
                length = writeString(user,this->buffer,length);
                if(pass != NULL) {
                    CHECK_STRING_LENGTH(length,pass)
                    length = writeString(pass,this->buffer,length);
                }
            }

            write(MQTTCONNECT,this->buffer,length-MQTT_MAX_HEADER_SIZE);

            lastInActivity = lastOutActivity = millis();

            while (!_client->available()) {
                unsigned long t = millis();
                if (t-lastInActivity >= ((int32_t) this->socketTimeout*1000UL)) {
                    _state = MQTT_CONNECTION_TIMEOUT;
                    _client->stop();
                    return false;
                }
            }
            uint8_t llen;
            uint32_t len = readPacket(&llen);

            if (len == 4) {
                if (buffer[3] == 0) {
                    lastInActivity = millis();
                    pingOutstanding = false;
                    _state = MQTT_CONNECTED;
                    return true;
                } else {
                    _state = buffer[3];
                }
            }
            _client->stop();
        } else {
            _state = MQTT_CONNECT_FAILED;
        }
        return false;
    }
    return true;
}

// reads a byte into result
boolean CollarMqtt::readByte(uint8_t * result) {
   uint32_t previousMillis = millis();
   while(!_client->available()) {
     yield();
     uint32_t currentMillis = millis();
     if(currentMillis - previousMillis >= ((int32_t) this->socketTimeout * 1000)){
       return false;
     }
   }
   *result = _client->read();
   return true;
}

// reads a byte into result[*index] and increments index
boolean CollarMqtt::readByte(uint8_t * result, uint16_t * index){
  uint16_t current_index = *index;
  uint8_t * write_address = &(result[current_index]);
  if(readByte(write_address)){
    *index = current_index + 1;
    return true;
  }
  return false;
}

uint32_t CollarMqtt::readPacket(uint8_t* lengthLength) {
    uint16_t len = 0;
    if(!readByte(this->buffer, &len)) return 0;
    bool isPublish = (this->buffer[0]&0xF0) == MQTTPUBLISH;
    uint32_t multiplier = 1;
    uint32_t length = 0;
    uint8_t digit = 0;
    uint16_t skip = 0;
    uint32_t start = 0;

    do {
        if (len == 5) {
            // Invalid remaining length encoding - kill the connection
            _state = MQTT_DISCONNECTED;
            _client->stop();
            return 0;
        }
        if(!readByte(&digit)) return 0;
        this->buffer[len++] = digit;
        length += (digit & 127) * multiplier;
        multiplier <<=7; //multiplier *= 128
    } while ((digit & 128) != 0);
    *lengthLength = len-1;

    if (isPublish) {
        // Read in topic length to calculate bytes to skip over for Stream writing
        if(!readByte(this->buffer, &len)) return 0;
        if(!readByte(this->buffer, &len)) return 0;
        skip = (this->buffer[*lengthLength+1]<<8)+this->buffer[*lengthLength+2];
        start = 2;
        if (this->buffer[0]&MQTTQOS1) {
            // skip message id
            skip += 2;
        }
    }
    uint32_t idx = len;

    for (uint32_t i = start;i<length;i++) {
        if(!readByte(&digit)) return 0;
        if (this->stream) {
            if (isPublish && idx-*lengthLength-2>skip) {
                this->stream->write(digit);
            }
        }

        if (len < this->bufferSize) {
            this->buffer[len] = digit;
            len++;
        }
        idx++;
    }

    if (!this->stream && idx > this->bufferSize) {
        len = 0; // This will cause the packet to be ignored.
    }
    return len;
}

boolean CollarMqtt::loop() {
    if (connected()) {
        unsigned long t = millis();
        if ((t - lastInActivity > this->keepAlive*1000UL) || (t - lastOutActivity > this->keepAlive*1000UL)) {
            if (pingOutstanding) {
                this->_state = MQTT_CONNECTION_TIMEOUT;
                _client->stop();
                return false;
            } else {
                this->buffer[0] = MQTTPINGREQ;
                this->buffer[1] = 0;
                _client->write(this->buffer,2);
                lastOutActivity = t;
                lastInActivity = t;
                pingOutstanding = true;
            }
        }
        if (_client->available()) {
            uint8_t llen;
            uint16_t len = readPacket(&llen);
            uint16_t msgId = 0;
            uint8_t *payload;
            if (len > 0) {
                lastInActivity = t;
                uint8_t type = this->buffer[0]&0xF0;
                if (type == MQTTPUBLISH) {
                    if (callback) {
                        uint16_t tl = (this->buffer[llen+1]<<8)+this->buffer[llen+2]; /* topic length in bytes */
                        memmove(this->buffer+llen+2,this->buffer+llen+3,tl); /* move topic inside buffer 1 byte to front */
                        this->buffer[llen+2+tl] = 0; /* end the topic as a 'C' string with \x00 */
                        char *topic = (char*) this->buffer+llen+2;
                        // msgId only present for QOS>0
                        if ((this->buffer[0]&0x06) == MQTTQOS1) {
                            msgId = (this->buffer[llen+3+tl]<<8)+this->buffer[llen+3+tl+1];
                            payload = this->buffer+llen+3+tl+2;
                            callback(topic,payload,len-llen-3-tl-2);

                            this->buffer[0] = MQTTPUBACK;
                            this->buffer[1] = 2;
                            this->buffer[2] = (msgId >> 8);
                            this->buffer[3] = (msgId & 0xFF);
                            _client->write(this->buffer,4);
                            lastOutActivity = t;

                        } else {
                            payload = this->buffer+llen+3+tl;
                            callback(topic,payload,len-llen-3-tl);
                        }
                    }
                } else if (type == MQTTPINGREQ) {
                    this->buffer[0] = MQTTPINGRESP;
                    this->buffer[1] = 0;
                    _client->write(this->buffer,2);
                } else if (type == MQTTPINGRESP) {
                    pingOutstanding = false;
                }
            } else if (!connected()) {
                // readPacket has closed the connection
                return false;
            }
        }
        return true;
    }
    return false;
}

boolean CollarMqtt::publish(const char* topic, const char* payload) {
    return publish(topic,(const uint8_t*)payload, payload ? strnlen(payload, this->bufferSize) : 0,false);
}

boolean CollarMqtt::publish(const char* topic, const char* payload, boolean retained) {
    return publish(topic,(const uint8_t*)payload, payload ? strnlen(payload, this->bufferSize) : 0,retained);
}

boolean CollarMqtt::publish(const char* topic, const uint8_t* payload, unsigned int plength) {
    return publish(topic, payload, plength, false);
}

boolean CollarMqtt::publish(const char* topic, const uint8_t* payload, unsigned int plength, boolean retained) {
    if (connected()) {
        if (this->bufferSize < MQTT_MAX_HEADER_SIZE + 2+strnlen(topic, this->bufferSize) + plength) {
            // Too long
            return false;
        }
        // Leave room in the buffer for header and variable length field
        uint16_t length = MQTT_MAX_HEADER_SIZE;
        length = writeString(topic,this->buffer,length);

        // Add payload
        uint16_t i;
        for (i=0;i<plength;i++) {
            this->buffer[length++] = payload[i];
        }

        // Write the header
        uint8_t header = MQTTPUBLISH;
        if (retained) {
            header |= 1;
        }
        return write(header,this->buffer,length-MQTT_MAX_HEADER_SIZE);
    }
    return false;
}

boolean CollarMqtt::publish_P(const char* topic, const char* payload, boolean retained) {
    return publish_P(topic, (const uint8_t*)payload, payload ? strnlen(payload, this->bufferSize) : 0, retained);
}

boolean CollarMqtt::publish_P(const char* topic, const uint8_t* payload, unsigned int plength, boolean retained) {
    uint8_t llen = 0;
    uint8_t digit;
    unsigned int rc = 0;
    uint16_t tlen;
    unsigned int pos = 0;
    unsigned int i;
    uint8_t header;
    unsigned int len;
    int expectedLength;

    if (!connected()) {
        return false;
    }

    tlen = strnlen(topic, this->bufferSize);

    header = MQTTPUBLISH;
    if (retained) {
        header |= 1;
    }
    this->buffer[pos++] = header;
    len = plength + 2 + tlen;
    do {
        digit = len  & 127; //digit = len %128
        len >>= 7; //len = len / 128
        if (len > 0) {
            digit |= 0x80;
        }
        this->buffer[pos++] = digit;
        llen++;
    } while(len>0);

    pos = writeString(topic,this->buffer,pos);

    rc += _client->write(this->buffer,pos);

    for (i=0;i<plength;i++) {
        rc += _client->write((char)pgm_read_byte_near(payload + i));
    }

    lastOutActivity = millis();

    expectedLength = 1 + llen + 2 + tlen + plength;

    return (rc == expectedLength);
}

boolean CollarMqtt::beginPublish(const char* topic, unsigned int plength, boolean retained) {
    // Local safety checks. Large outgoing WAVs use this streaming API only.
    if (!topic || strlen(topic)+2+MQTT_MAX_HEADER_SIZE > this->bufferSize ||
        plength > 128044U) return false;
    if (connected()) {
        // Send the header and variable length field
        uint16_t length = MQTT_MAX_HEADER_SIZE;
        length = writeString(topic,this->buffer,length);
        uint8_t header = MQTTPUBLISH;
        if (retained) {
            header |= 1;
        }
        size_t hlen = buildHeader(header, this->buffer, plength+length-MQTT_MAX_HEADER_SIZE);
        uint16_t rc = _client->write(this->buffer+(MQTT_MAX_HEADER_SIZE-hlen),length-(MQTT_MAX_HEADER_SIZE-hlen));
        lastOutActivity = millis();
        return (rc == (length-(MQTT_MAX_HEADER_SIZE-hlen)));
    }
    return false;
}

int CollarMqtt::endPublish() {
 return 1;
}

size_t CollarMqtt::write(uint8_t data) {
    lastOutActivity = millis();
    return _client->write(data);
}

size_t CollarMqtt::write(const uint8_t *buffer, size_t size) {
    lastOutActivity = millis();
    return _client->write(buffer,size);
}

size_t CollarMqtt::buildHeader(uint8_t header, uint8_t* buf, uint32_t length) {
    uint8_t lenBuf[4];
    uint8_t llen = 0;
    uint8_t digit;
    uint8_t pos = 0;
    uint32_t len = length;
    do {

        digit = len  & 127; //digit = len %128
        len >>= 7; //len = len / 128
        if (len > 0) {
            digit |= 0x80;
        }
        lenBuf[pos++] = digit;
        llen++;
    } while(len>0);

    buf[4-llen] = header;
    for (int i=0;i<llen;i++) {
        buf[MQTT_MAX_HEADER_SIZE-llen+i] = lenBuf[i];
    }
    return llen+1; // Full header size is variable length bit plus the 1-byte fixed header
}

boolean CollarMqtt::write(uint8_t header, uint8_t* buf, uint16_t length) {
    uint16_t rc;
    uint8_t hlen = buildHeader(header, buf, length);

#ifdef MQTT_MAX_TRANSFER_SIZE
    uint8_t* writeBuf = buf+(MQTT_MAX_HEADER_SIZE-hlen);
    uint16_t bytesRemaining = length+hlen;  //Match the length type
    uint8_t bytesToWrite;
    boolean result = true;
    while((bytesRemaining > 0) && result) {
        bytesToWrite = (bytesRemaining > MQTT_MAX_TRANSFER_SIZE)?MQTT_MAX_TRANSFER_SIZE:bytesRemaining;
        rc = _client->write(writeBuf,bytesToWrite);
        result = (rc == bytesToWrite);
        bytesRemaining -= rc;
        writeBuf += rc;
    }
    return result;
#else
    rc = _client->write(buf+(MQTT_MAX_HEADER_SIZE-hlen),length+hlen);
    lastOutActivity = millis();
    return (rc == hlen+length);
#endif
}

boolean CollarMqtt::subscribe(const char* topic) {
    return subscribe(topic, 0);
}

boolean CollarMqtt::subscribe(const char* topic, uint8_t qos) {
    size_t topicLength = strnlen(topic, this->bufferSize);
    if (topic == 0) {
        return false;
    }
    if (qos > 1) {
        return false;
    }
    if (this->bufferSize < 9 + topicLength) {
        // Too long
        return false;
    }
    if (connected()) {
        // Leave room in the buffer for header and variable length field
        uint16_t length = MQTT_MAX_HEADER_SIZE;
        nextMsgId++;
        if (nextMsgId == 0) {
            nextMsgId = 1;
        }
        this->buffer[length++] = (nextMsgId >> 8);
        this->buffer[length++] = (nextMsgId & 0xFF);
        length = writeString((char*)topic, this->buffer,length);
        this->buffer[length++] = qos;
        return write(MQTTSUBSCRIBE|MQTTQOS1,this->buffer,length-MQTT_MAX_HEADER_SIZE);
    }
    return false;
}

boolean CollarMqtt::unsubscribe(const char* topic) {
	size_t topicLength = strnlen(topic, this->bufferSize);
    if (topic == 0) {
        return false;
    }
    if (this->bufferSize < 9 + topicLength) {
        // Too long
        return false;
    }
    if (connected()) {
        uint16_t length = MQTT_MAX_HEADER_SIZE;
        nextMsgId++;
        if (nextMsgId == 0) {
            nextMsgId = 1;
        }
        this->buffer[length++] = (nextMsgId >> 8);
        this->buffer[length++] = (nextMsgId & 0xFF);
        length = writeString(topic, this->buffer,length);
        return write(MQTTUNSUBSCRIBE|MQTTQOS1,this->buffer,length-MQTT_MAX_HEADER_SIZE);
    }
    return false;
}

void CollarMqtt::disconnect() {
    this->buffer[0] = MQTTDISCONNECT;
    this->buffer[1] = 0;
    _client->write(this->buffer,2);
    _state = MQTT_DISCONNECTED;
    _client->flush();
    _client->stop();
    lastInActivity = lastOutActivity = millis();
}

uint16_t CollarMqtt::writeString(const char* string, uint8_t* buf, uint16_t pos) {
    const char* idp = string;
    uint16_t i = 0;
    pos += 2;
    while (*idp) {
        buf[pos++] = *idp++;
        i++;
    }
    buf[pos-i-2] = (i >> 8);
    buf[pos-i-1] = (i & 0xFF);
    return pos;
}


boolean CollarMqtt::connected() {
    boolean rc;
    if (_client == NULL ) {
        rc = false;
    } else {
        rc = (int)_client->connected();
        if (!rc) {
            if (this->_state == MQTT_CONNECTED) {
                this->_state = MQTT_CONNECTION_LOST;
                _client->flush();
                _client->stop();
            }
        } else {
            return this->_state == MQTT_CONNECTED;
        }
    }
    return rc;
}

CollarMqtt& CollarMqtt::setServer(uint8_t * ip, uint16_t port) {
    IPAddress addr(ip[0],ip[1],ip[2],ip[3]);
    return setServer(addr,port);
}

CollarMqtt& CollarMqtt::setServer(IPAddress ip, uint16_t port) {
    this->ip = ip;
    this->port = port;
    this->domain = NULL;
    return *this;
}

CollarMqtt& CollarMqtt::setServer(const char * domain, uint16_t port) {
    this->domain = domain;
    this->port = port;
    return *this;
}

CollarMqtt& CollarMqtt::setCallback(MQTT_CALLBACK_SIGNATURE) {
    this->callback = callback;
    return *this;
}

CollarMqtt& CollarMqtt::setClient(Client& client){
    this->_client = &client;
    return *this;
}

CollarMqtt& CollarMqtt::setStream(Stream& stream){
    this->stream = &stream;
    return *this;
}

int CollarMqtt::state() {
    return this->_state;
}

boolean CollarMqtt::setBufferSize(uint16_t size) {
    if (size == 0) {
        // Cannot set it back to 0
        return false;
    }
    if (this->bufferSize == 0) {
        this->buffer = (uint8_t*)malloc(size);
    } else {
        uint8_t* newBuffer = (uint8_t*)realloc(this->buffer, size);
        if (newBuffer != NULL) {
            this->buffer = newBuffer;
        } else {
            return false;
        }
    }
    this->bufferSize = size;
    return (this->buffer != NULL);
}

uint16_t CollarMqtt::getBufferSize() {
    return this->bufferSize;
}
CollarMqtt& CollarMqtt::setKeepAlive(uint16_t keepAlive) {
    this->keepAlive = keepAlive;
    return *this;
}
CollarMqtt& CollarMqtt::setSocketTimeout(uint16_t timeout) {
    this->socketTimeout = timeout;
    return *this;
}
// END EMBEDDED CollarMqtt.cpp

// BEGIN MILO MODEL
#include <stdint.h>
static constexpr int MILO_COUNT = 7;
static constexpr int MILO_MAX_FRAMES = 40;
static constexpr float MILO_THRESHOLD = 4.500000000e-02f;
static constexpr float MILO_ENERGY_FLOOR = 2.126095886e+02f;
static const char MILO_MODEL_ID[] = "63aeffbdedfb";
static const float MILO_WINDOW[320] = {0.000000000e+00f,9.698494978e-05f,3.879021679e-04f,8.726387750e-04f,1.551006804e-03f,2.422743011e-03f,3.487509210e-03f,4.744892474e-03f,6.194404792e-03f,7.835484110e-03f,9.667493403e-03f,1.168972254e-02f,1.390138641e-02f,1.630162634e-02f,1.888951287e-02f,2.166404203e-02f,2.462413721e-02f,2.776864730e-02f,3.109635599e-02f,3.460597247e-02f,3.829612955e-02f,4.216540605e-02f,4.621228948e-02f,5.043521896e-02f,5.483255163e-02f,5.940258130e-02f,6.414353848e-02f,6.905357540e-02f,7.413079590e-02f,7.937323302e-02f,8.477884531e-02f,9.034553915e-02f,9.607115388e-02f,1.019534692e-01f,1.079901978e-01f,1.141790077e-01f,1.205174923e-01f,1.270031929e-01f,1.336335987e-01f,1.404061168e-01f,1.473181546e-01f,1.543669999e-01f,1.615499258e-01f,1.688641608e-01f,1.763068587e-01f,1.838751286e-01f,1.915660203e-01f,1.993765831e-01f,2.073037624e-01f,2.153444886e-01f,2.234956473e-01f,2.317540795e-01f,2.401165664e-01f,2.485798746e-01f,2.571407259e-01f,2.657957673e-01f,2.745417058e-01f,2.833750844e-01f,2.922925055e-01f,3.012904823e-01f,3.103655577e-01f,3.195142150e-01f,3.287328780e-01f,3.380180001e-01f,3.473659456e-01f,3.567731082e-01f,3.662358224e-01f,3.757504523e-01f,3.853132725e-01f,3.949205875e-01f,4.045686424e-01f,4.142537415e-01f,4.239721000e-01f,4.337199628e-01f,4.434935153e-01f,4.532890022e-01f,4.631026089e-01f,4.729305506e-01f,4.827689826e-01f,4.926140904e-01f,5.024620295e-01f,5.123090744e-01f,5.221512914e-01f,5.319849849e-01f,5.418062210e-01f,5.516112447e-01f,5.613962412e-01f,5.711573958e-01f,5.808910131e-01f,5.905932188e-01f,6.002602577e-01f,6.098884344e-01f,6.194739342e-01f,6.290131211e-01f,6.385022402e-01f,6.479376554e-01f,6.573156714e-01f,6.666326523e-01f,6.758849621e-01f,6.850690842e-01f,6.941813827e-01f,7.032183409e-01f,7.121765018e-01f,7.210523486e-01f,7.298424244e-01f,7.385433316e-01f,7.471516728e-01f,7.556641698e-01f,7.640774846e-01f,7.723883390e-01f,7.805935144e-01f,7.886898518e-01f,7.966741920e-01f,8.045434356e-01f,8.122945428e-01f,8.199245334e-01f,8.274303675e-01f,8.348091841e-01f,8.420581222e-01f,8.491743803e-01f,8.561551571e-01f,8.629977703e-01f,8.696995378e-01f,8.762578964e-01f,8.826702833e-01f,8.889342546e-01f,8.950473070e-01f,9.010071158e-01f,9.068113565e-01f,9.124578238e-01f,9.179442525e-01f,9.232684970e-01f,9.284285903e-01f,9.334224463e-01f,9.382482171e-01f,9.429039359e-01f,9.473878145e-01f,9.516981244e-01f,9.558332562e-01f,9.597915411e-01f,9.635714293e-01f,9.671714902e-01f,9.705902934e-01f,9.738265872e-01f,9.768790603e-01f,9.797464609e-01f,9.824278355e-01f,9.849219918e-01f,9.872280955e-01f,9.893451333e-01f,9.912723303e-01f,9.930089712e-01f,9.945543408e-01f,9.959078431e-01f,9.970690012e-01f,9.980372787e-01f,9.988123775e-01f,9.993939400e-01f,9.997817874e-01f,9.999757409e-01f,9.999757409e-01f,9.997817874e-01f,9.993939400e-01f,9.988123775e-01f,9.980372787e-01f,9.970690012e-01f,9.959078431e-01f,9.945543408e-01f,9.930089712e-01f,9.912723303e-01f,9.893451333e-01f,9.872280955e-01f,9.849219918e-01f,9.824278355e-01f,9.797464609e-01f,9.768790603e-01f,9.738265872e-01f,9.705902934e-01f,9.671714902e-01f,9.635714293e-01f,9.597915411e-01f,9.558332562e-01f,9.516981244e-01f,9.473878145e-01f,9.429039359e-01f,9.382482171e-01f,9.334224463e-01f,9.284285903e-01f,9.232684970e-01f,9.179442525e-01f,9.124578238e-01f,9.068113565e-01f,9.010071158e-01f,8.950473070e-01f,8.889342546e-01f,8.826702833e-01f,8.762578964e-01f,8.696995378e-01f,8.629977703e-01f,8.561551571e-01f,8.491743803e-01f,8.420581222e-01f,8.348091841e-01f,8.274303675e-01f,8.199245334e-01f,8.122945428e-01f,8.045434356e-01f,7.966741920e-01f,7.886898518e-01f,7.805935144e-01f,7.723883390e-01f,7.640774846e-01f,7.556641698e-01f,7.471516728e-01f,7.385433316e-01f,7.298424244e-01f,7.210523486e-01f,7.121765018e-01f,7.032183409e-01f,6.941813827e-01f,6.850690842e-01f,6.758849621e-01f,6.666326523e-01f,6.573156714e-01f,6.479376554e-01f,6.385022402e-01f,6.290131211e-01f,6.194739342e-01f,6.098884344e-01f,6.002602577e-01f,5.905932188e-01f,5.808910131e-01f,5.711573958e-01f,5.613962412e-01f,5.516112447e-01f,5.418062210e-01f,5.319849849e-01f,5.221512914e-01f,5.123090744e-01f,5.024620295e-01f,4.926140904e-01f,4.827689826e-01f,4.729305506e-01f,4.631026089e-01f,4.532890022e-01f,4.434935153e-01f,4.337199628e-01f,4.239721000e-01f,4.142537415e-01f,4.045686424e-01f,3.949205875e-01f,3.853132725e-01f,3.757504523e-01f,3.662358224e-01f,3.567731082e-01f,3.473659456e-01f,3.380180001e-01f,3.287328780e-01f,3.195142150e-01f,3.103655577e-01f,3.012904823e-01f,2.922925055e-01f,2.833750844e-01f,2.745417058e-01f,2.657957673e-01f,2.571407259e-01f,2.485798746e-01f,2.401165664e-01f,2.317540795e-01f,2.234956473e-01f,2.153444886e-01f,2.073037624e-01f,1.993765831e-01f,1.915660203e-01f,1.838751286e-01f,1.763068587e-01f,1.688641608e-01f,1.615499258e-01f,1.543669999e-01f,1.473181546e-01f,1.404061168e-01f,1.336335987e-01f,1.270031929e-01f,1.205174923e-01f,1.141790077e-01f,1.079901978e-01f,1.019534692e-01f,9.607115388e-02f,9.034553915e-02f,8.477884531e-02f,7.937323302e-02f,7.413079590e-02f,6.905357540e-02f,6.414353848e-02f,5.940258130e-02f,5.483255163e-02f,5.043521896e-02f,4.621228948e-02f,4.216540605e-02f,3.829612955e-02f,3.460597247e-02f,3.109635599e-02f,2.776864730e-02f,2.462413721e-02f,2.166404203e-02f,1.888951287e-02f,1.630162634e-02f,1.390138641e-02f,1.168972254e-02f,9.667493403e-03f,7.835484110e-03f,6.194404792e-03f,4.744892474e-03f,3.487509210e-03f,2.422743011e-03f,1.551006804e-03f,8.726387750e-04f,3.879021679e-04f,9.698494978e-05f,0.000000000e+00f};
static const float MILO_MEL[20][257] = {
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,2.651858032e-01f,5.966680646e-01f,9.281502962e-01f,7.677376866e-01f,4.711999893e-01f,1.746622920e-01f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,2.322623283e-01f,5.288000107e-01f,8.253377080e-01f,8.909726143e-01f,6.256956458e-01f,3.604187071e-01f,9.514176846e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.090273932e-01f,3.743043244e-01f,6.395812631e-01f,9.048582315e-01f,8.478003144e-01f,6.104886532e-01f,3.731769621e-01f,1.358652711e-01f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.521996856e-01f,3.895113766e-01f,6.268230677e-01f,8.641347289e-01f,9.092479944e-01f,6.969534755e-01f,4.846589863e-01f,2.723644674e-01f,6.006998196e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,9.075202793e-02f,3.030465245e-01f,5.153410435e-01f,7.276355028e-01f,9.399300218e-01f,8.638228774e-01f,6.739082336e-01f,4.839936495e-01f,2.940790653e-01f,1.041644588e-01f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.361771375e-01f,3.260917366e-01f,5.160063505e-01f,7.059209347e-01f,8.958355188e-01f,9.232895374e-01f,7.533956170e-01f,5.835016370e-01f,4.136076570e-01f,2.437136769e-01f,7.381971180e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,7.671044022e-02f,2.466044128e-01f,4.164983630e-01f,5.863923430e-01f,7.562863231e-01f,9.261803031e-01f,9.140537977e-01f,7.620698810e-01f,6.100860238e-01f,4.581021070e-01f,3.061182201e-01f,1.541343182e-01f,2.150413115e-03f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,8.594619483e-02f,2.379300892e-01f,3.899140060e-01f,5.418978930e-01f,6.938818097e-01f,8.458656669e-01f,9.978495836e-01f,8.659618497e-01f,7.299999595e-01f,5.940380692e-01f,4.580761492e-01f,3.221142590e-01f,1.861523837e-01f,5.019048601e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.340381652e-01f,2.700000703e-01f,4.059619606e-01f,5.419238210e-01f,6.778857112e-01f,8.138476014e-01f,9.498094916e-01f,9.232705235e-01f,8.016416430e-01f,6.800127029e-01f,5.583838224e-01f,4.367549121e-01f,3.151260018e-01f,1.934970915e-01f,7.186818123e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,7.672946155e-02f,1.983583719e-01f,3.199872673e-01f,4.416161776e-01f,5.632451177e-01f,6.848739982e-01f,8.065028787e-01f,9.281318188e-01f,9.554849863e-01f,8.466781378e-01f,7.378712296e-01f,6.290643215e-01f,5.202574134e-01f,4.114505351e-01f,3.026436269e-01f,1.938367337e-01f,8.502984047e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,4.451499134e-02f,1.533218920e-01f,2.621287704e-01f,3.709356785e-01f,4.797425866e-01f,5.885494947e-01f,6.973563433e-01f,8.061632514e-01f,9.149701595e-01f,9.787294865e-01f,8.813929558e-01f,7.840563655e-01f,6.867197752e-01f,5.893832445e-01f,4.920466542e-01f,3.947100937e-01f,2.973735034e-01f,2.000369430e-01f,1.027003750e-01f,5.363801960e-03f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,2.127050236e-02f,1.186070740e-01f,2.159436345e-01f,3.132802248e-01f,4.106167853e-01f,5.079533458e-01f,6.052899361e-01f,7.026264668e-01f,7.999630570e-01f,8.972996473e-01f,9.946361780e-01f,9.177229404e-01f,8.306474686e-01f,7.435720563e-01f,6.564966440e-01f,5.694211721e-01f,4.823457599e-01f,3.952703178e-01f,3.081948757e-01f,2.211194485e-01f,1.340440065e-01f,4.696857557e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,8.227708191e-02f,1.693525165e-01f,2.564279437e-01f,3.435033858e-01f,4.305788279e-01f,5.176542401e-01f,6.047297120e-01f,6.918051243e-01f,7.788805366e-01f,8.659560084e-01f,9.530314207e-01f,9.641211629e-01f,8.862251639e-01f,8.083291054e-01f,7.304331064e-01f,6.525371075e-01f,5.746410489e-01f,4.967450500e-01f,4.188490212e-01f,3.409530222e-01f,2.630569935e-01f,1.851609796e-01f,1.072649583e-01f,2.936893888e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,3.587882966e-02f,1.137748510e-01f,1.916708648e-01f,2.695668936e-01f,3.474628925e-01f,4.253589213e-01f,5.032549500e-01f,5.811509490e-01f,6.590470076e-01f,7.369430065e-01f,8.148390055e-01f,8.927350640e-01f,9.706310630e-01f,9.565886259e-01f,8.869042993e-01f,8.172200322e-01f,7.475357056e-01f,6.778514385e-01f,6.081671715e-01f,5.384828448e-01f,4.687985778e-01f,3.991142809e-01f,3.294299841e-01f,2.597457170e-01f,1.900614202e-01f,1.203771234e-01f,5.069283396e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,4.341139644e-02f,1.130956858e-01f,1.827799827e-01f,2.524642646e-01f,3.221485615e-01f,3.918328583e-01f,4.615171254e-01f,5.312014222e-01f,6.008856893e-01f,6.705700159e-01f,7.402542830e-01f,8.099386096e-01f,8.796228766e-01f,9.493071437e-01f,9.830105901e-01f,9.206723571e-01f,8.583341241e-01f,7.959958911e-01f,7.336576581e-01f,6.713194251e-01f,6.089811921e-01f,5.466429591e-01f,4.843047261e-01f,4.219664931e-01f,3.596282601e-01f,2.972900271e-01f,2.349518090e-01f,1.726135761e-01f,1.102753356e-01f,4.793710262e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.698939316e-02f,7.932762802e-02f,1.416658610e-01f,2.040040940e-01f,2.663423419e-01f,3.286805749e-01f,3.910188079e-01f,4.533570409e-01f,5.156952739e-01f,5.780335069e-01f,6.403717399e-01f,7.027099729e-01f,7.650482059e-01f,8.273864388e-01f,8.897246718e-01f,9.520629048e-01f,9.871170521e-01f,9.313504100e-01f,8.755838275e-01f,8.198172450e-01f,7.640506625e-01f,7.082840800e-01f,6.525174975e-01f,5.967508554e-01f,5.409842730e-01f,4.852176905e-01f,4.294511080e-01f,3.736844957e-01f,3.179179132e-01f,2.621513307e-01f,2.063847333e-01f,1.506181359e-01f,9.485154599e-02f,3.908495605e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.288297679e-02f,6.864956766e-02f,1.244161576e-01f,1.801827550e-01f,2.359493524e-01f,2.917159498e-01f,3.474825323e-01f,4.032491148e-01f,4.590157270e-01f,5.147823095e-01f,5.705488920e-01f,6.263154745e-01f,6.820820570e-01f,7.378486991e-01f,7.936152816e-01f,8.493818641e-01f,9.051484466e-01f,9.609150290e-01f,9.850769043e-01f,9.351891875e-01f,8.853014708e-01f,8.354137540e-01f,7.855260372e-01f,7.356382608e-01f,6.857505441e-01f,6.358628273e-01f,5.859751105e-01f,5.360873938e-01f,4.861996472e-01f,4.363119304e-01f,3.864241838e-01f,3.365364671e-01f,2.866487503e-01f,2.367610186e-01f,1.868732870e-01f,1.369855553e-01f,8.709783107e-02f,3.721010685e-02f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.492307335e-02f,6.481079757e-02f,1.146985292e-01f,1.645862609e-01f,2.144739777e-01f,2.643617094e-01f,3.142494261e-01f,3.641371727e-01f,4.140248895e-01f,4.639126062e-01f,5.138003230e-01f,5.636880994e-01f,6.135758162e-01f,6.634635329e-01f,7.133512497e-01f,7.632389665e-01f,8.131266832e-01f,8.630144596e-01f,9.129021764e-01f,9.627898932e-01f,9.886588454e-01f,9.440302253e-01f,8.994016051e-01f,8.547730446e-01f,8.101444244e-01f,7.655158043e-01f,7.208871841e-01f,6.762585640e-01f,6.316300035e-01f,5.870013833e-01f,5.423727632e-01f,4.977441728e-01f,4.531155527e-01f,4.084869325e-01f,3.638583422e-01f,3.192297220e-01f,2.746011317e-01f,2.299725115e-01f,1.853439063e-01f,1.407153010e-01f,9.608669579e-02f,5.145808682e-02f,6.829481572e-03f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,1.134115737e-02f,5.596976355e-02f,1.005983725e-01f,1.452269852e-01f,1.898555905e-01f,2.344841957e-01f,2.791128159e-01f,3.237414062e-01f,3.683700264e-01f,4.129986167e-01f,4.576272368e-01f,5.022558570e-01f,5.468844175e-01f,5.915130377e-01f,6.361416578e-01f,6.807702780e-01f,7.253988981e-01f,7.700274587e-01f,8.146560788e-01f,8.592846990e-01f,9.039133191e-01f,9.485419393e-01f,9.931704998e-01f,9.661856294e-01f,9.262617230e-01f,8.863378167e-01f,8.464139104e-01f,8.064900041e-01f,7.665661573e-01f,7.266422510e-01f,6.867183447e-01f,6.467944384e-01f,6.068705320e-01f,5.669466257e-01f,5.270227194e-01f,4.870988429e-01f,4.471749365e-01f,4.072510302e-01f,3.673271537e-01f,3.274032474e-01f,2.874793410e-01f,2.475554347e-01f,2.076315433e-01f,1.677076370e-01f,1.277837455e-01f,8.785984665e-02f,4.793594778e-02f,8.012047969e-03f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f},
{0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,3.381437436e-02f,7.373827696e-02f,1.136621758e-01f,1.535860747e-01f,1.935099661e-01f,2.334338725e-01f,2.733577788e-01f,3.132816553e-01f,3.532055616e-01f,3.931294680e-01f,4.330533743e-01f,4.729772508e-01f,5.129011869e-01f,5.528250337e-01f,5.927489400e-01f,6.326728463e-01f,6.725967526e-01f,7.125206590e-01f,7.524445653e-01f,7.923684716e-01f,8.322923779e-01f,8.722162843e-01f,9.121401310e-01f,9.520640373e-01f,9.919879436e-01f,9.714522958e-01f,9.357371330e-01f,9.000219703e-01f,8.643068075e-01f,8.285916448e-01f,7.928764820e-01f,7.571613193e-01f,7.214461565e-01f,6.857309937e-01f,6.500158310e-01f,6.143007278e-01f,5.785855651e-01f,5.428704023e-01f,5.071552396e-01f,4.714400768e-01f,4.357249141e-01f,4.000097513e-01f,3.642945886e-01f,3.285794556e-01f,2.928642929e-01f,2.571491301e-01f,2.214339674e-01f,1.857188195e-01f,1.500036567e-01f,1.142885014e-01f,7.857334614e-02f,4.285818711e-02f,7.143031340e-03f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f,0.000000000e+00f}
};
static const float MILO_DCT[12][20] = {
{9.969173074e-01f,9.723699093e-01f,9.238795042e-01f,8.526401520e-01f,7.604059577e-01f,6.494480371e-01f,5.224985480e-01f,3.826834261e-01f,2.334453613e-01f,7.845909894e-02f,-7.845909894e-02f,-2.334453613e-01f,-3.826834261e-01f,-5.224985480e-01f,-6.494480371e-01f,-7.604059577e-01f,-8.526401520e-01f,-9.238795042e-01f,-9.723699093e-01f,-9.969173074e-01f},
{9.876883626e-01f,8.910065293e-01f,7.071067691e-01f,4.539904892e-01f,1.564344615e-01f,-1.564344615e-01f,-4.539904892e-01f,-7.071067691e-01f,-8.910065293e-01f,-9.876883626e-01f,-9.876883626e-01f,-8.910065293e-01f,-7.071067691e-01f,-4.539904892e-01f,-1.564344615e-01f,1.564344615e-01f,4.539904892e-01f,7.071067691e-01f,8.910065293e-01f,9.876883626e-01f},
{9.723699093e-01f,7.604059577e-01f,3.826834261e-01f,-7.845909894e-02f,-5.224985480e-01f,-8.526401520e-01f,-9.969173074e-01f,-9.238795042e-01f,-6.494480371e-01f,-2.334453613e-01f,2.334453613e-01f,6.494480371e-01f,9.238795042e-01f,9.969173074e-01f,8.526401520e-01f,5.224985480e-01f,7.845909894e-02f,-3.826834261e-01f,-7.604059577e-01f,-9.723699093e-01f},
{9.510565400e-01f,5.877852440e-01f,6.123234263e-17f,-5.877852440e-01f,-9.510565400e-01f,-9.510565400e-01f,-5.877852440e-01f,-1.836970147e-16f,5.877852440e-01f,9.510565400e-01f,9.510565400e-01f,5.877852440e-01f,3.061616999e-16f,-5.877852440e-01f,-9.510565400e-01f,-9.510565400e-01f,-5.877852440e-01f,-4.286263852e-16f,5.877852440e-01f,9.510565400e-01f},
{9.238795042e-01f,3.826834261e-01f,-3.826834261e-01f,-9.238795042e-01f,-9.238795042e-01f,-3.826834261e-01f,3.826834261e-01f,9.238795042e-01f,9.238795042e-01f,3.826834261e-01f,-3.826834261e-01f,-9.238795042e-01f,-9.238795042e-01f,-3.826834261e-01f,3.826834261e-01f,9.238795042e-01f,9.238795042e-01f,3.826834261e-01f,-3.826834261e-01f,-9.238795042e-01f},
{8.910065293e-01f,1.564344615e-01f,-7.071067691e-01f,-9.876883626e-01f,-4.539904892e-01f,4.539904892e-01f,9.876883626e-01f,7.071067691e-01f,-1.564344615e-01f,-8.910065293e-01f,-8.910065293e-01f,-1.564344615e-01f,7.071067691e-01f,9.876883626e-01f,4.539904892e-01f,-4.539904892e-01f,-9.876883626e-01f,-7.071067691e-01f,1.564344615e-01f,8.910065293e-01f},
{8.526401520e-01f,-7.845909894e-02f,-9.238795042e-01f,-7.604059577e-01f,2.334453613e-01f,9.723699093e-01f,6.494480371e-01f,-3.826834261e-01f,-9.969173074e-01f,-5.224985480e-01f,5.224985480e-01f,9.969173074e-01f,3.826834261e-01f,-6.494480371e-01f,-9.723699093e-01f,-2.334453613e-01f,7.604059577e-01f,9.238795042e-01f,7.845909894e-02f,-8.526401520e-01f},
{8.090170026e-01f,-3.090170026e-01f,-1.000000000e+00f,-3.090170026e-01f,8.090170026e-01f,8.090170026e-01f,-3.090170026e-01f,-1.000000000e+00f,-3.090170026e-01f,8.090170026e-01f,8.090170026e-01f,-3.090170026e-01f,-1.000000000e+00f,-3.090170026e-01f,8.090170026e-01f,8.090170026e-01f,-3.090170026e-01f,-1.000000000e+00f,-3.090170026e-01f,8.090170026e-01f},
{7.604059577e-01f,-5.224985480e-01f,-9.238795042e-01f,2.334453613e-01f,9.969173074e-01f,7.845909894e-02f,-9.723699093e-01f,-3.826834261e-01f,8.526401520e-01f,6.494480371e-01f,-6.494480371e-01f,-8.526401520e-01f,3.826834261e-01f,9.723699093e-01f,-7.845909894e-02f,-9.969173074e-01f,-2.334453613e-01f,9.238795042e-01f,5.224985480e-01f,-7.604059577e-01f},
{7.071067691e-01f,-7.071067691e-01f,-7.071067691e-01f,7.071067691e-01f,7.071067691e-01f,-7.071067691e-01f,-7.071067691e-01f,7.071067691e-01f,7.071067691e-01f,-7.071067691e-01f,-7.071067691e-01f,7.071067691e-01f,7.071067691e-01f,-7.071067691e-01f,-7.071067691e-01f,7.071067691e-01f,7.071067691e-01f,-7.071067691e-01f,-7.071067691e-01f,7.071067691e-01f},
{6.494480371e-01f,-8.526401520e-01f,-3.826834261e-01f,9.723699093e-01f,7.845909894e-02f,-9.969173074e-01f,2.334453613e-01f,9.238795042e-01f,-5.224985480e-01f,-7.604059577e-01f,7.604059577e-01f,5.224985480e-01f,-9.238795042e-01f,-2.334453613e-01f,9.969173074e-01f,-7.845909894e-02f,-9.723699093e-01f,3.826834261e-01f,8.526401520e-01f,-6.494480371e-01f},
{5.877852440e-01f,-9.510565400e-01f,-1.836970147e-16f,9.510565400e-01f,-5.877852440e-01f,-5.877852440e-01f,9.510565400e-01f,5.510910704e-16f,-9.510565400e-01f,5.877852440e-01f,5.877852440e-01f,-9.510565400e-01f,-2.694841886e-15f,9.510565400e-01f,-5.877852440e-01f,-5.877852440e-01f,9.510565400e-01f,-4.904777104e-16f,-9.510565400e-01f,5.877852440e-01f}
};
static const int8_t MILO_T0[16][12] = {
{103,63,36,13,9,2,5,1,-5,1,2,-1},
{122,23,-10,-8,-10,-1,-7,1,1,10,14,-13},
{122,-1,-2,12,-20,-3,-9,6,9,7,3,-23},
{120,5,5,5,-31,-3,4,11,10,4,8,-21},
{111,31,18,2,-19,-24,-13,19,25,3,-5,-21},
{114,27,25,6,-28,-15,-7,13,19,-4,-3,-14},
{110,39,31,12,-20,-16,1,1,12,2,-8,-24},
{109,51,21,21,-3,-16,-5,-7,4,-6,-4,-20},
{108,49,24,16,-12,-12,-1,-18,6,1,-2,-24},
{112,31,39,6,-20,-9,-8,-22,4,4,7,-12},
{119,32,-3,7,-9,-13,-8,-3,6,5,12,-17},
{118,37,-13,-8,-11,-2,3,-8,2,2,13,-11},
{121,35,-11,-10,-6,3,3,-6,1,0,8,-2},
{119,41,1,-6,-12,-5,2,-3,-2,-1,0,1},
{115,40,11,6,-19,-22,-1,5,-1,11,11,2},
{115,49,7,-7,-1,1,5,8,12,8,8,-1}
};
static const int8_t MILO_T1[17][12] = {
{104,61,29,18,8,11,9,-5,-6,-2,1,1},
{121,28,1,-1,-7,-6,5,10,9,18,7,-13},
{119,19,-5,4,-25,-20,1,-1,16,1,4,-18},
{121,18,11,10,-24,-9,-4,3,15,-4,2,-5},
{115,21,29,10,-27,-19,-11,7,10,-5,5,-11},
{111,33,22,25,-14,-32,-11,-5,9,-2,-7,-8},
{113,39,18,17,-1,-26,-13,-14,5,-3,-1,-5},
{114,34,26,14,-1,-18,-23,-13,-1,-1,-5,-4},
{114,36,21,14,-7,-17,-26,-9,0,5,4,-7},
{121,29,0,2,-6,-15,-6,-8,6,9,6,-13},
{120,32,-7,-2,-4,-6,-11,-6,10,10,2,-11},
{122,29,1,4,-8,-11,-2,-5,-1,11,7,-9},
{117,41,4,-3,-17,-12,1,-1,0,9,10,-6},
{118,43,3,-5,-15,-6,3,-1,-2,6,6,-5},
{118,40,9,-7,-18,-8,0,3,4,2,4,-2},
{117,46,11,-2,-13,-6,2,4,4,1,0,1},
{118,41,11,9,-3,-10,7,8,4,3,3,1}
};
static const int8_t MILO_T2[40][12] = {
{105,45,31,31,18,21,10,9,-8,-10,0,-2},
{108,40,32,38,8,3,9,1,-9,-4,0,0},
{120,29,-4,13,-9,-20,-3,-3,10,6,0,6},
{117,24,-4,17,-10,-28,-1,17,15,0,-5,-8},
{116,33,16,9,-13,-16,-10,10,23,-1,-9,-5},
{113,18,22,25,-27,-21,-9,10,20,-12,2,-4},
{106,37,38,13,-24,-30,-4,-6,19,-3,-1,-8},
{106,48,25,29,-10,-27,-7,-8,3,-8,3,-4},
{106,51,28,22,-1,-23,-12,-9,6,-10,-4,-9},
{107,40,41,13,-15,-15,-18,-6,13,1,-7,-11},
{108,35,42,2,-22,-24,-11,1,7,-5,5,-9},
{117,41,2,5,-13,-14,-4,-3,4,2,13,-9},
{122,26,-11,6,-5,-8,4,-6,-9,2,15,-7},
{122,29,-7,-1,0,-7,5,-2,-14,0,9,2},
{122,32,-5,-1,-9,2,2,-4,-7,-4,9,2},
{120,33,-6,1,-14,-6,10,0,-9,-7,5,-3},
{116,44,12,4,-8,-5,16,-4,-12,-4,-1,-8},
{117,47,2,6,-4,0,-2,1,-4,-6,5,5},
{117,44,14,4,-7,-4,6,-1,-7,-11,1,2},
{123,25,9,8,5,0,4,2,5,12,6,0},
{121,28,10,10,-1,5,13,7,0,5,15,5},
{119,31,8,14,12,9,19,6,-2,5,6,6},
{118,36,-9,0,1,13,14,2,11,6,-15,-12},
{114,26,23,25,10,6,22,16,13,6,9,-8},
{120,25,21,17,6,-6,-9,-11,-4,-2,-2,-15},
{124,19,-3,4,9,12,1,5,8,1,9,8},
{122,3,7,15,10,9,21,5,2,7,-13,-10},
{115,43,-3,7,-2,-15,14,12,-4,15,6,-12},
{114,43,6,4,-9,7,-9,-15,11,9,-21,-12},
{117,17,-9,20,8,11,23,9,30,1,-1,2},
{119,34,15,11,-7,5,5,6,14,2,-10,-7},
{118,4,5,13,1,14,15,26,23,15,1,-2},
{116,18,9,34,2,12,25,13,9,1,-6,-11},
{116,17,9,35,9,6,19,6,-12,-2,-13,-16},
{119,-3,-1,28,-7,6,23,5,-8,-4,-1,-20},
{118,2,2,28,0,-2,18,12,-17,15,-8,-19},
{118,24,0,15,-20,-10,18,10,-13,-1,-6,-15},
{119,22,-6,31,-1,-2,-1,-5,-14,11,8,-10},
{121,20,1,19,-5,-3,13,1,1,16,5,-10},
{115,18,2,26,-5,3,30,17,17,2,-13,-15}
};
static const int8_t MILO_T3[23][12] = {
{114,46,29,10,7,5,4,-4,7,5,0,0},
{121,26,-17,-10,-7,1,-3,-1,12,13,6,-8},
{119,22,-25,-2,-11,-9,-9,1,14,10,1,-15},
{122,21,-16,3,-8,-13,-3,5,12,5,-1,-9},
{120,10,-5,10,-18,-20,-9,11,17,1,-11,-11},
{120,25,-1,3,-14,-15,-12,0,17,2,1,-14},
{112,40,15,2,-31,-14,-19,4,2,-1,4,-11},
{116,33,9,12,-9,-28,-19,-2,-4,0,-6,-5},
{113,38,23,14,-14,-22,-14,-7,10,7,-14,-5},
{115,27,16,27,-11,-24,-12,-11,5,-1,-8,-7},
{112,34,26,24,-10,-21,-11,-7,-6,8,-2,-17},
{114,14,44,7,-11,-2,-23,-16,1,4,3,-8},
{120,17,21,6,-16,-12,4,-10,-2,9,6,-14},
{123,19,8,7,-4,-8,-1,-3,-10,3,11,-16},
{123,29,2,-1,6,-5,-2,0,-2,-1,11,-10},
{121,34,7,-6,2,-4,3,0,-12,-2,11,-8},
{120,39,4,0,-4,-2,4,-1,-1,-6,-2,-4},
{120,32,4,0,-14,-3,5,4,-11,-7,12,-6},
{116,45,18,-5,-15,-5,3,-2,-6,-8,1,-1},
{119,41,2,-5,-4,0,4,3,-8,-11,-6,2},
{120,37,8,0,-7,-6,9,-3,-7,-9,-3,-5},
{118,42,12,-4,-9,-8,3,0,-8,-3,-8,-5},
{115,47,20,8,-7,-11,1,1,-7,0,-6,-3}
};
static const int8_t MILO_T4[14][12] = {
{107,43,33,37,11,-5,12,-1,-9,5,2,-4},
{113,37,26,27,-2,-9,-5,4,-15,-9,6,-3},
{122,8,-15,7,-3,-4,-11,9,10,11,10,-20},
{114,21,7,11,-31,-8,-8,18,17,7,-5,-25},
{112,26,11,4,-36,-12,-20,20,16,7,2,-15},
{112,27,26,11,-32,-15,-9,6,21,8,-4,-14},
{115,39,18,24,-16,-13,-2,-4,6,2,2,-9},
{96,66,23,28,-1,-9,-5,-10,8,-13,1,-26},
{103,62,15,22,-2,-14,-3,1,10,-6,3,-24},
{103,60,8,19,-5,-21,-6,-3,14,-3,11,-26},
{118,30,0,8,0,-19,-15,-7,8,13,14,-15},
{120,32,-3,12,-8,-13,-2,-5,0,11,12,-5},
{120,37,2,0,-2,-12,-7,-6,0,9,7,-5},
{116,45,13,14,-4,-12,-5,-5,2,6,1,4}
};
static const int8_t MILO_T5[23][12] = {
{110,54,20,18,5,12,16,-1,-4,0,0,-4},
{116,48,-4,-2,-6,7,-1,-3,-1,4,9,-5},
{119,37,-10,-7,0,-5,-4,3,11,8,6,-9},
{121,28,-14,0,-6,2,-9,4,15,2,2,-11},
{119,35,-11,10,-17,-9,0,9,9,-3,2,-6},
{120,33,4,3,-11,-13,-6,6,13,2,0,-9},
{111,51,2,-8,-17,-10,-8,-1,23,3,5,-10},
{111,51,15,-8,-20,-16,4,11,13,2,-4,-3},
{113,46,22,21,-7,-6,4,-9,9,1,1,-5},
{106,52,28,29,5,-19,-3,2,3,-5,-9,-7},
{109,48,23,26,13,-9,-6,2,6,-11,-16,-13},
{108,31,48,18,4,-3,-20,-8,13,-3,-6,-15},
{117,34,15,2,-17,-6,-1,-6,19,10,-1,-15},
{120,18,-5,-2,-13,-11,-3,2,23,20,8,-10},
{120,25,-9,-8,-7,-7,-14,-7,8,13,13,-11},
{118,25,-5,-12,-13,-12,-6,-5,8,21,19,-10},
{119,34,-2,-9,-5,-18,3,-9,-3,11,12,-5},
{120,36,0,-9,-8,-6,-7,-8,-5,4,9,5},
{113,50,1,-8,-15,-3,-3,-11,-10,1,15,6},
{119,37,3,-11,-8,-5,-6,-10,-8,0,7,10},
{117,40,1,-11,-14,-7,-1,-10,-10,-3,12,10},
{118,41,-1,-11,-9,-10,-2,-7,-8,-3,8,5},
{115,47,0,-5,-15,-9,4,-3,-12,-2,9,0}
};
static const int8_t MILO_T6[25][12] = {
{111,46,23,21,9,10,15,-2,-5,-4,6,-9},
{116,41,25,12,0,-8,4,9,0,8,6,-4},
{119,20,-23,12,-1,-15,-6,-9,9,11,3,-18},
{118,19,-17,12,-14,-22,-11,7,19,2,-6,-15},
{118,24,-5,1,-17,-26,0,14,11,-6,3,-13},
{118,31,8,-7,-20,-22,-4,7,15,-1,3,-6},
{109,28,35,-7,-32,-25,1,-6,20,3,1,-3},
{111,38,24,4,-26,-31,-3,-3,12,8,-7,2},
{110,52,31,1,-4,-20,-2,-1,0,3,-5,4},
{107,48,40,10,-5,-21,-11,-9,-5,8,-4,0},
{109,51,25,8,3,-26,-9,-5,-2,9,-5,-10},
{121,22,7,3,-6,-14,-19,-12,7,12,3,-10},
{120,21,-10,10,-2,-14,-14,-17,-3,16,12,-9},
{122,25,-4,2,-5,-6,-7,-12,-10,8,14,0},
{119,34,3,-9,-6,-5,-2,-10,-17,1,14,6},
{120,34,9,-1,-11,-6,-10,-5,-10,4,10,-2},
{114,46,20,-2,-19,-10,-6,-1,-3,-8,3,1},
{119,40,10,0,-8,-9,-1,-5,-8,-2,7,-2},
{116,46,5,0,-11,-4,-4,-3,-14,-5,11,5},
{118,40,10,-3,-13,-9,1,1,-11,-8,6,6},
{116,48,7,-10,-9,-1,3,-8,-8,-6,7,1},
{117,46,3,-5,-11,-2,-3,-2,-7,-6,5,2},
{118,41,7,-7,-12,-1,3,-4,-7,-8,5,3},
{118,43,4,-7,-9,-7,-1,-2,-2,-9,5,-2},
{116,49,13,-2,-9,-4,-1,1,-5,-5,5,6}
};
static const int8_t * const MILO_TEMPLATES[] = {&MILO_T0[0][0],&MILO_T1[0][0],&MILO_T2[0][0],&MILO_T3[0][0],&MILO_T4[0][0],&MILO_T5[0][0],&MILO_T6[0][0]};
static const int MILO_LENGTHS[7] = {16,17,40,23,14,23,25};
// END MILO MODEL

// BEGIN EMBEDDED MiloMatcher.h
#include <math.h>
#include <stdint.h>
#include <string.h>

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
// END EMBEDDED MiloMatcher.h

// BEGIN EMBEDDED MiloCapture.h
#include <Arduino.h>
#include <esp_timer.h>
#include <atomic>

// One clip, stored in four 32 kB blocks: no contiguous 128 kB allocation needed.
// Idle history occupies the SAME blocks as the final clip; no second audio copy.
class MiloCapture {
 public:
  static constexpr uint32_t FRAME_SAMPLES=320, FRAME_BYTES=640;
  static constexpr uint32_t HISTORY=70, POST_LIMIT=130, MAX_FRAMES=200;
  struct Clip {
    uint32_t session, id, frames, preFrames, preStart, epoch, readyMs;
    uint64_t timestampUs;
    float distance;
    bool truncated;
  };
 private:
  enum Phase { IDLE, CAPTURING, READY, SENDING, RESET };
  std::atomic<int> phase{IDLE};
  std::atomic<bool> online{false};
  std::atomic<uint32_t> epoch{0};
  uint8_t *blocks[4]={};
  Clip clip{};
  uint32_t session=0, nextId=0, head=0, filled=0, silence=0, post=0;
  MiloMatcher matcher;
  uint8_t *physical(uint32_t frame) {
    return blocks[frame/50]+(frame%50)*FRAME_BYTES;
  }
  void resetCapture() {
    head=filled=silence=post=0;
    matcher.reset();
    phase.store(IDLE);
  }
 public:
  uint32_t readGaps=0, computeOverruns=0, abortedClips=0, busyFrames=0;
  float bestSinceStatus=1e9f;

  bool begin(uint32_t bootId) {
    session=bootId;
    for (int i=0;i<4;++i) {
      blocks[i]=static_cast<uint8_t *>(malloc(50*FRAME_BYTES));
      if (!blocks[i]) {
        for (int j=0;j<i;++j) { free(blocks[j]);blocks[j]=nullptr; }
        return false;
      }
    }
    matcher.reset();
    return true;
  }
  // Network task owns link changes. The epoch invalidates captures spanning an outage.
  void setOnline(bool value) {
    if (online.load()!=value) {
      epoch.fetch_add(1);
      online.store(value);
    }
  }
  bool connected() const { return online.load(); }
  bool fresh(const Clip &c) const {
    return online.load() && c.epoch==epoch.load() && uint32_t(millis()-c.readyMs)<5000;
  }
  bool take(Clip &out) {
    int expected=READY;
    if (!phase.compare_exchange_strong(expected,SENDING)) return false;
    out=clip; return true;
  }
  void release() { phase.store(RESET); } // called ONLY after network has finished reading
  void discardReady() {
    int expected=READY;
    phase.compare_exchange_strong(expected,RESET);
  }
  const uint8_t *frame(const Clip &c,uint32_t i) {
    return physical(i<c.preFrames ? (c.preStart+i)%HISTORY : i);
  }
  static void put16(uint8_t *p,uint16_t v) { p[0]=v;p[1]=v>>8; }
  static void put32(uint8_t *p,uint32_t v) {
    for (int i=0;i<4;++i) p[i]=(v>>(8*i))&255;
  }
  static void wavHeader(uint8_t *out,uint32_t frames) {
    const uint32_t bytes=frames*FRAME_BYTES;
    memset(out,0,44);
    memcpy(out,"RIFF",4);put32(out+4,36+bytes);
    memcpy(out+8,"WAVEfmt ",8);put32(out+16,16);
    put16(out+20,1);put16(out+22,1);put32(out+24,16000);
    put32(out+28,32000);put16(out+32,2);put16(out+34,16);
    memcpy(out+36,"data",4);put32(out+40,bytes);
  }
  void gap() {
    ++readGaps;
    int p=phase.load();
    // Never touch a completed buffer owned by the network task.
    if (p==IDLE || p==CAPTURING || p==RESET) {
      if (p==CAPTURING) ++abortedClips;
      resetCapture();
    }
  }
  void feed(const int16_t *pcm,float rms) {
    const uint64_t before=esp_timer_get_time();
    int p=phase.load();
    if (p==RESET) { resetCapture();p=IDLE; }
    if (p==READY || p==SENDING) { ++busyFrames;return; }
    if (p==CAPTURING && (!online.load() || clip.epoch!=epoch.load())) {
      ++abortedClips;resetCapture();p=IDLE;
    }
    if (p==CAPTURING) {
      memcpy(physical(clip.frames++),pcm,FRAME_BYTES);
      ++post;
      silence=rms<MILO_ENERGY_FLOOR ? silence+1 : 0;
      if (silence>=30 || post>=POST_LIMIT) {
        clip.truncated=post>=POST_LIMIT;
        clip.readyMs=millis();
        phase.store(READY); // release publishes immutable data/metadata to network
        matcher.reset();
      }
    } else {
      memcpy(physical(head),pcm,FRAME_BYTES);
      head=(head+1)%HISTORY;
      if (filled<HISTORY) ++filled;
      const float score=matcher.feed(pcm,rms);
      if (score<bestSinceStatus) bestSinceStatus=score;
      if (MILO_COUNT>0 && score<=MILO_THRESHOLD && online.load()) {
        clip.session=session;clip.id=++nextId;
        clip.frames=clip.preFrames=filled;
        clip.preStart=(head+HISTORY-filled)%HISTORY;
        clip.epoch=epoch.load();clip.distance=score;clip.truncated=false;
        const uint64_t historyUs=uint64_t(filled)*20000;
        clip.timestampUs=before>historyUs ? before-historyUs : 0;
        post=silence=0;
        phase.store(CAPTURING);
      }
    }
    if (esp_timer_get_time()-before>20000) ++computeOverruns;
  }
};
// END EMBEDDED MiloCapture.h

// Microphone sampling and network tasks
I2SClass microphone;
WiFiClient wifiClient;
CollarMqtt mqtt(wifiClient);
MiloCapture milo;
struct MicSample {
  uint32_t sequence;
  uint64_t timestampUs;
  float rms;
  uint32_t peak;
  bool valid;
  float wakeDistance;
  uint32_t abortedClips,readGaps,computeOverruns,busyFrames;
};
QueueHandle_t micQueue;
void forceMqttReconnect() {
  milo.setOnline(false);
  wifiClient.stop();
  digitalWrite(LED_BUILTIN,LOW);
}

// Audio gain MUST match Collar_Recorder. No Serial PCM in this operational sketch.
void microphoneTask(void *parameter) {
  int32_t raw[320];
  int16_t pcm[320];
  uint32_t seq=0,lastPublish=millis(),lastPrint=0;
  for (;;) {
    const size_t bytes=microphone.readBytes(reinterpret_cast<char *>(raw),sizeof(raw));
    if (bytes!=sizeof(raw)) {
      milo.gap();
      MicSample failed{}; failed.sequence=seq++;
      failed.timestampUs=esp_timer_get_time(); failed.wakeDistance=1e9f;
      failed.abortedClips=milo.abortedClips;failed.readGaps=milo.readGaps;
      failed.computeOverruns=milo.computeOverruns;failed.busyFrames=milo.busyFrames;
      xQueueOverwrite(micQueue,&failed);
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    double sum=0,squares=0; uint32_t peak=0;
    for (int i=0;i<320;++i) {
      const int32_t value=(raw[i]>>16)*4;
      pcm[i]=constrain(value,-32768,32767);
      sum+=pcm[i]; squares+=double(pcm[i])*pcm[i];
      peak=max(peak,uint32_t(abs(int32_t(pcm[i]))));
    }
    double mean=sum/320;
    double variance=squares/320-mean*mean;
    float rms=sqrt(variance>0?variance:0);
    milo.feed(pcm,rms);
    if (millis()-lastPublish>=MIC_PUBLISH_MS) {
      MicSample sample{};
      sample.sequence=seq++; sample.timestampUs=esp_timer_get_time();
      sample.rms=rms;sample.peak=peak;sample.valid=true;
      sample.wakeDistance=milo.bestSinceStatus;
      sample.abortedClips=milo.abortedClips;sample.readGaps=milo.readGaps;
      sample.computeOverruns=milo.computeOverruns;sample.busyFrames=milo.busyFrames;
      xQueueOverwrite(micQueue,&sample);
      milo.bestSinceStatus=1e9f;lastPublish=millis();
      if (millis()-lastPrint>=1000) {
        Serial.printf("# mic rms=%.1f peak=%lu model=%s aborted=%lu gaps=%lu overruns=%lu\n",
          rms,(unsigned long)peak,MILO_MODEL_ID,(unsigned long)milo.abortedClips,
          (unsigned long)milo.readGaps,(unsigned long)milo.computeOverruns);
        lastPrint=millis();
      }
    }
  }
}

bool publishMicrophone(const MicSample &sample) {
  char payload[500], distance[32];
  if (sample.wakeDistance<1e8f) snprintf(distance,sizeof(distance),"%.6f",sample.wakeDistance);
  else strcpy(distance,"null");
  const int length=snprintf(payload,sizeof(payload),
    "{\"schema_version\":1,\"type\":\"microphone_level\",\"source_id\":\"collar\","
    "\"seq\":%lu,\"timestamp_us\":%llu,\"sample_rate_hz\":16000,\"rms\":%.1f,"
    "\"peak\":%lu,\"valid\":%s,\"model_id\":\"%s\",\"wake_distance\":%s,"
    "\"wake_threshold\":%.6f,\"aborted_clips\":%lu,\"read_gaps\":%lu,\"compute_overruns\":%lu,\"busy_ms\":%lu,\"free_heap\":%lu}",
    (unsigned long)sample.sequence,(unsigned long long)sample.timestampUs,sample.rms,
    (unsigned long)sample.peak,sample.valid?"true":"false",MILO_MODEL_ID,distance,
    MILO_THRESHOLD,(unsigned long)sample.abortedClips,(unsigned long)sample.readGaps,
    (unsigned long)sample.computeOverruns,(unsigned long)(sample.busyFrames*20),
    (unsigned long)ESP.getFreeHeap());
  return length>0 && length<int(sizeof(payload)) && mqtt.publish(MIC_TOPIC,payload,false);
}

// Called only by networkTask: one MQTT PUBLISH contains a whole RIFF/WAV.
// No other MQTT operation may interleave between beginPublish and endPublish.
bool publishWav(const MiloCapture::Clip &clip) {
  if (!clip.frames || clip.frames>MiloCapture::MAX_FRAMES) return false;
  char topic[100];
  snprintf(topic,sizeof(topic),"sensor/collar/voice/wav/%08lx/%lu",
           (unsigned long)clip.session,(unsigned long)clip.id);
  uint8_t header[44];MiloCapture::wavHeader(header,clip.frames);
  const uint32_t bytes=44+clip.frames*MiloCapture::FRAME_BYTES;
  const uint32_t started=millis();
  if (!mqtt.beginPublish(topic,bytes,false)) return false;
  if (mqtt.write(header,sizeof(header))!=sizeof(header)) return false;
  for (uint32_t i=0;i<clip.frames;++i) {
    if (millis()-started>8000 || WiFi.status()!=WL_CONNECTED) return false;
    if (mqtt.write(milo.frame(clip,i),MiloCapture::FRAME_BYTES)!=MiloCapture::FRAME_BYTES)
      return false;
    // Let the continuous microphone reader/idle task run. This is still ONE MQTT message.
    if (i%8==7) vTaskDelay(pdMS_TO_TICKS(1));
  }
  if (!mqtt.endPublish()) return false;
  Serial.printf("# WAV written: %s bytes=%lu upload_ms=%lu truncated=%s\n",
     topic,(unsigned long)bytes,(unsigned long)(millis()-started),clip.truncated?"true":"false");
  // Optional metadata is separate; the WAV is independently usable without it.
  char info[650];
  int n=snprintf(info,sizeof(info),
    "{\"schema_version\":2,\"type\":\"voice_candidate\",\"source_id\":\"collar\","
    "\"wav_topic\":\"%s\",\"session_id\":%lu,\"clip_id\":%lu,"
    "\"timestamp_us\":%llu,\"model_id\":\"%s\",\"distance\":%.6f,"
    "\"sample_rate_hz\":16000,\"format\":\"wav_pcm_s16le\","
    "\"duration_ms\":%lu,\"wav_bytes\":%lu,\"truncated\":%s}",
    topic,(unsigned long)clip.session,(unsigned long)clip.id,
    (unsigned long long)clip.timestampUs,MILO_MODEL_ID,clip.distance,
    (unsigned long)(clip.frames*20),(unsigned long)bytes,clip.truncated?"true":"false");
  return n>0 && n<int(sizeof(info)) && mqtt.publish("sensor/collar/voice/event",info,false);
}

void networkTask(void *parameter) {
  uint32_t wifiAttemptStarted = 0;
  uint32_t lastMqttAttempt = 0;
  uint32_t lastStatusPrint = 0;
  uint32_t lastLedToggle = 0;

  bool previousWiFiConnected = false;
  bool ledState = false;

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);

  // Reliability-first setting for this test.
  WiFi.setSleep(false);

  mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  if (!mqtt.setBufferSize(1024)) {
    Serial.println("# ERROR: MQTT buffer allocation failed");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  // Keep-alive leaves headroom for one bounded WAV send.
  mqtt.setKeepAlive(15);
  wifiClient.setTimeout(1000);
  mqtt.setSocketTimeout(1);

  // Start the first Wi-Fi attempt immediately.
  Serial.println("# Starting Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  wifiAttemptStarted = millis();

  for (;;) {
    uint32_t now = millis();
    bool wifiConnected =
        WiFi.status() == WL_CONNECTED;

    if (!wifiConnected) {
      if (previousWiFiConnected) {
        previousWiFiConnected = false;
        forceMqttReconnect();
      }

      // Drop completed offline clips; active captures abort on link epoch change.
      milo.setOnline(false);
      milo.discardReady();

      // Fast LED blink: Wi-Fi is disconnected.
      if (now - lastLedToggle >= 250) {
        lastLedToggle = now;
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
      }

      // Print diagnostic status every five seconds.
      if (now - lastStatusPrint >= 5000) {
        lastStatusPrint = now;

        Serial.print("# Wi-Fi waiting, status=");
        Serial.println(WiFi.status());
      }

      // Give each attempt 20 seconds before restarting it.
      if (now - wifiAttemptStarted >= 20000) {
        Serial.println("# Restarting Wi-Fi attempt");

        WiFi.disconnect(false);
        vTaskDelay(pdMS_TO_TICKS(250));

        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        wifiAttemptStarted = millis();
      }
    } else {
      if (!previousWiFiConnected) {
        previousWiFiConnected = true;

        // Wi-Fi may have recovered while an old TCP socket remained.
        // Always begin this Wi-Fi session with a clean MQTT transport.
        forceMqttReconnect();

        Serial.print("# Wi-Fi connected, IP=");
        Serial.println(WiFi.localIP());

        Serial.print("# Wi-Fi RSSI=");
        Serial.println(WiFi.RSSI());

        // Permit an immediate MQTT attempt.
        lastMqttAttempt = now - MQTT_RETRY_MS;
      }

      if (!mqtt.connected()) {
        milo.setOnline(false);
      milo.discardReady();
        // Slow LED blink: Wi-Fi works, MQTT does not.
        if (now - lastLedToggle >= 1000) {
          lastLedToggle = now;
          ledState = !ledState;
          digitalWrite(LED_BUILTIN, ledState);
        }

        if (now - lastMqttAttempt >= MQTT_RETRY_MS) {
          lastMqttAttempt = now;

          char clientId[40];
          snprintf(clientId,sizeof(clientId),"collar-%012llx",
                   (unsigned long long)ESP.getEfuseMac());

          Serial.print("# MQTT connection attempt to ");
          Serial.println(MQTT_BROKER_IP);

          if (mqtt.connect(
                clientId,
                CONNECTION_TOPIC,
                1,
                true,
                CONNECTION_OFFLINE_PAYLOAD)) {

            if (mqtt.publish(
                  CONNECTION_TOPIC,
                  CONNECTION_ONLINE_PAYLOAD,
                  true)) {

              // Discard old level summaries after reconnect.

              xQueueReset(micQueue);

              milo.setOnline(true);
              Serial.printf("# MQTT connected; free_heap=%lu\n",(unsigned long)ESP.getFreeHeap());
            } else {
              Serial.println("# MQTT online publish failed");
              forceMqttReconnect();
            }
          } else {
            Serial.print("# MQTT failed, state=");
            Serial.println(mqtt.state());
          }
        }
      } else {
        // mqtt.loop() detects keep-alive and broker failures.
        // A failure must close the socket so the next pass reconnects.
        if (!mqtt.loop()) {
          forceMqttReconnect();
          vTaskDelay(pdMS_TO_TICKS(20));
          continue;
        }

        MicSample micSample;
        if (xQueueReceive(micQueue, &micSample, 0) == pdTRUE) {
          if (!publishMicrophone(micSample)) {
            forceMqttReconnect();
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
          }
        }

        MiloCapture::Clip clip;
        if (milo.take(clip)) {
          const bool ok=milo.fresh(clip) && publishWav(clip);
          milo.release(); // microphone may reuse audio memory only now
          if (!ok) {
            Serial.println("# WAV dropped/send failed; no automatic replay");
            forceMqttReconnect();
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
          }
        }

        // Solid LED only after this pass completed successfully.
        digitalWrite(LED_BUILTIN, HIGH);
        ledState = true;
      }
    }

    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_BUILTIN,OUTPUT);
  digitalWrite(LED_BUILTIN,LOW);
  micQueue=xQueueCreate(1,sizeof(MicSample));
  if (!micQueue || !milo.begin(esp_random())) {
    Serial.println("# ERROR: 128 kB audio storage allocation failed; not starting");
    while (true) delay(1000);
  }
  microphone.setPins(MIC_BCLK,MIC_WS,-1,MIC_SD);
  if (!microphone.begin(I2S_MODE_STD,MIC_RATE,I2S_DATA_BIT_WIDTH_32BIT,
                         I2S_SLOT_MODE_MONO,I2S_STD_SLOT_LEFT)) {
    Serial.println("# ERROR: INMP441 initialization failed");
    while (true) delay(1000);
  }
  Serial.printf("# Collar microphone ready; model=%s; free_heap=%lu\n",
                MILO_MODEL_ID,(unsigned long)ESP.getFreeHeap());
  if (MILO_COUNT==0)
    Serial.println("# UNTRAINED: levels work; no voice clips until enrollment and re-upload.");
  if (xTaskCreatePinnedToCore(microphoneTask,"collarAudio",8192,nullptr,2,nullptr,1)!=pdPASS ||
      xTaskCreatePinnedToCore(networkTask,"collarNetwork",8192,nullptr,1,nullptr,0)!=pdPASS) {
    Serial.println("# ERROR: task creation failed; reset after checking memory");
    while (true) delay(1000);
  }
}
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
