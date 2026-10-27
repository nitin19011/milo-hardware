// Demo firmware: records continuously and publishes each completed four-second WAV.
// No wake-word model, command recognition, or loudness gate.
#include <Arduino.h>
#include "ESP_I2S.h"
#include <WiFi.h>

const char WIFI_SSID[]     = "Nitin";
const char WIFI_PASSWORD[] = "CHANGE_ME_PRIVATE";
const char MQTT_BROKER_IP[] = "172.20.10.2";
const uint16_t MQTT_BROKER_PORT = 1883;
const uint32_t MQTT_RETRY_MS = 5000;
const char CONNECTION_TOPIC[] = "status/collar/connection";
const char CONNECTION_ONLINE_PAYLOAD[] = "{\"type\":\"connection_status\",\"state\":\"ONLINE\"}";
const char CONNECTION_OFFLINE_PAYLOAD[] = "{\"type\":\"connection_status\",\"state\":\"OFFLINE\"}";

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


// INMP441: VDD -> 3V3, GND and L/R -> GND. Pin numbers are GPIO numbers.
const int MIC_BCLK = 14, MIC_WS = 17, MIC_SD = 16;
const uint32_t SAMPLE_RATE = 16000;
const uint32_t FRAME_SAMPLES = 320; // 20 ms
const uint32_t BLOCK_SAMPLES = 16000; // one second of signed 16-bit PCM
const uint32_t BLOCK_BYTES = BLOCK_SAMPLES * sizeof(int16_t);
const uint8_t BLOCK_COUNT = 5; // four seconds plus one second of upload headroom
const uint8_t CLIP_BLOCKS = 4;
const uint8_t NO_BLOCK = 255;

I2SClass microphone;
WiFiClient wifiClient;
CollarMqtt mqtt(wifiClient);
int16_t *audioBlocks[BLOCK_COUNT] = {};
QueueHandle_t freeBlocks, readyClips;
uint32_t sessionId;

struct AudioClip {
  uint8_t blocks[CLIP_BLOCKS];
  uint32_t id;
  uint32_t finishedMs;
};

// Explicit declarations keep Arduino's automatic prototype generation unambiguous.
void releaseClip(AudioClip &clip);
void makeWavHeader(uint8_t *header);
void microphoneTask(void *parameter);
bool publishWav(AudioClip &clip);
void networkTask(void *parameter);

void releaseClip(AudioClip &clip) {
  for (uint8_t &block : clip.blocks) {
    if (block != NO_BLOCK) {
      xQueueSend(freeBlocks, &block, 0);
      block = NO_BLOCK;
    }
  }
}

void makeWavHeader(uint8_t *header) {
  const uint32_t dataBytes = CLIP_BLOCKS * BLOCK_BYTES;
  memset(header, 0, 44);
  memcpy(header, "RIFF", 4);
  uint32_t riffBytes = dataBytes + 36;
  memcpy(header + 4, &riffBytes, 4);
  memcpy(header + 8, "WAVEfmt ", 8);
  uint32_t fmtBytes = 16, rate = SAMPLE_RATE, byteRate = SAMPLE_RATE * 2;
  uint16_t format = 1, channels = 1, alignment = 2, bits = 16;
  // ESP32 is little-endian, as required by PCM WAV.
  memcpy(header + 16, &fmtBytes, 4);
  memcpy(header + 20, &format, 2);
  memcpy(header + 22, &channels, 2);
  memcpy(header + 24, &rate, 4);
  memcpy(header + 28, &byteRate, 4);
  memcpy(header + 32, &alignment, 2);
  memcpy(header + 34, &bits, 2);
  memcpy(header + 36, "data", 4);
  memcpy(header + 40, &dataBytes, 4);
}

void microphoneTask(void *parameter) {
  int32_t raw[FRAME_SAMPLES];
  AudioClip clip = {{NO_BLOCK, NO_BLOCK, NO_BLOCK, NO_BLOCK}, 0, 0};
  uint32_t frames = 0, nextId = 0, dropped = 0, readGaps = 0;
  uint32_t peak = 0;
  bool discard = false;
  for (;;) {
    size_t bytes = microphone.readBytes(reinterpret_cast<char *>(raw), sizeof(raw));
    if (bytes != sizeof(raw)) {
      // Never publish a WAV containing missing/uninitialized samples.
      releaseClip(clip);
      frames = 0; peak = 0; discard = false;
      Serial.printf("# Audio read gap: %lu; restarting four-second recording\n",
                    (unsigned long)++readGaps);
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    const uint32_t samplesSoFar = frames * FRAME_SAMPLES;
    const uint8_t blockIndex = samplesSoFar / BLOCK_SAMPLES;
    const uint32_t offset = samplesSoFar % BLOCK_SAMPLES;
    if (!discard && offset == 0 &&
        xQueueReceive(freeBlocks, &clip.blocks[blockIndex], 0) != pdTRUE) {
      // The network is too slow. Keep reading the mic, but drop this entire window.
      releaseClip(clip);
      discard = true;
    }
    if (!discard) {
      int16_t *destination = audioBlocks[clip.blocks[blockIndex]] + offset;
      for (uint32_t i = 0; i < FRAME_SAMPLES; ++i) {
        // Same gain as the previously tested recorder and collar firmware.
        int32_t value = (raw[i] >> 16) * 4;
        destination[i] = constrain(value, -32768, 32767);
        peak = max(peak, uint32_t(abs(int32_t(destination[i]))));
      }
    }
    if (++frames == SAMPLE_RATE * CLIP_BLOCKS / FRAME_SAMPLES) {
      clip.id = ++nextId;
      if (clip.id == 0) clip.id = ++nextId;
      clip.finishedMs = millis();
      if (discard || xQueueSend(readyClips, &clip, 0) != pdTRUE) {
        releaseClip(clip);
        Serial.printf("# Recording dropped: network/buffer busy; total=%lu\n",
                      (unsigned long)++dropped);
      } else {
        // Ownership has moved to the network task; it releases each block after sending.
        for (uint8_t &block : clip.blocks) block = NO_BLOCK;
        Serial.printf("# Recorded 4 s: clip=%lu peak=%lu\n",
                      (unsigned long)clip.id, (unsigned long)peak);
      }
      frames = 0; peak = 0; discard = false;
    }
  }
}

bool publishWav(AudioClip &clip) {
  char topic[100];
  snprintf(topic, sizeof(topic), "sensor/collar/voice/wav/%08lx/%lu",
           (unsigned long)sessionId, (unsigned long)clip.id);
  uint8_t header[44];
  makeWavHeader(header);
  const uint32_t started = millis();
  // These writes are parts of ONE MQTT message, not separate audio messages.
  if (!mqtt.beginPublish(topic, sizeof(header) + CLIP_BLOCKS * BLOCK_BYTES, false)) return false;
  if (mqtt.write(header, sizeof(header)) != sizeof(header)) return false;
  for (uint8_t i = 0; i < CLIP_BLOCKS; ++i) {
    const uint8_t *data = reinterpret_cast<const uint8_t *>(audioBlocks[clip.blocks[i]]);
    for (uint32_t offset = 0; offset < BLOCK_BYTES; offset += FRAME_SAMPLES * 2) {
      if (WiFi.status() != WL_CONNECTED || millis() - started > 3000) return false;
      if (mqtt.write(data + offset, FRAME_SAMPLES * 2) != FRAME_SAMPLES * 2) return false;
      if ((offset / (FRAME_SAMPLES * 2)) % 8 == 7) vTaskDelay(pdMS_TO_TICKS(1));
    }
    // Free this second of audio immediately so the mic can keep recording.
    xQueueSend(freeBlocks, &clip.blocks[i], 0);
    clip.blocks[i] = NO_BLOCK;
  }
  if (!mqtt.endPublish()) return false;
  Serial.printf("# WAV sent: %s bytes=128044 upload_ms=%lu\n",
                topic, (unsigned long)(millis() - started));
  return true;
}

void networkTask(void *parameter) {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  wifiClient.setTimeout(1000);
  mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(1);
  if (!mqtt.setBufferSize(1024)) {
    Serial.println("# ERROR: MQTT memory allocation failed; reset board");
    while (true) vTaskDelay(pdMS_TO_TICKS(1000));
  }
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t wifiStarted = millis(), lastStatus = 0;
  uint32_t lastMqttAttempt = millis() - MQTT_RETRY_MS;
  bool previouslyConnected = false;
  for (;;) {
    const uint32_t now = millis();
    if (WiFi.status() != WL_CONNECTED) {
      wifiClient.stop();
      previouslyConnected = false;
      if (now - lastStatus >= 5000) {
        Serial.printf("# Wi-Fi waiting, status=%d\n", int(WiFi.status()));
        lastStatus = now;
      }
      if (now - wifiStarted >= 20000) {
        WiFi.disconnect(false);
        vTaskDelay(pdMS_TO_TICKS(250));
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        wifiStarted = millis();
      }
    } else {
      if (!previouslyConnected) {
        previouslyConnected = true;
        wifiClient.stop();
        Serial.print("# Wi-Fi connected, IP="); Serial.println(WiFi.localIP());
        lastMqttAttempt = now - MQTT_RETRY_MS;
      }
      if (!mqtt.connected() && now - lastMqttAttempt >= MQTT_RETRY_MS) {
        lastMqttAttempt = now;
        char clientId[40];
        snprintf(clientId, sizeof(clientId), "collar-%012llx", (unsigned long long)ESP.getEfuseMac());
        Serial.print("# MQTT connecting to "); Serial.println(MQTT_BROKER_IP);
        if (mqtt.connect(clientId, CONNECTION_TOPIC, 1, true, CONNECTION_OFFLINE_PAYLOAD) &&
            mqtt.publish(CONNECTION_TOPIC, CONNECTION_ONLINE_PAYLOAD, true)) {
          Serial.printf("# MQTT connected; free_heap=%lu\n", (unsigned long)ESP.getFreeHeap());
        } else {
          Serial.printf("# MQTT failed, state=%d\n", mqtt.state());
          wifiClient.stop();
        }
      }
      if (mqtt.connected() && !mqtt.loop()) wifiClient.stop();
    }
    AudioClip clip;
    if (xQueueReceive(readyClips, &clip, 0) == pdTRUE) {
      if (WiFi.status() == WL_CONNECTED && mqtt.connected() && millis() - clip.finishedMs < 1000) {
        if (!publishWav(clip)) {
          // Close a partial MQTT message before any retry or other publish.
          wifiClient.stop();
          Serial.println("# WAV send failed; clip dropped, no replay");
        }
      } else {
        Serial.println("# WAV dropped: offline or stale; no replay");
      }
      releaseClip(clip);
    }
    digitalWrite(LED_BUILTIN, mqtt.connected() ? HIGH : LOW);
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  freeBlocks = xQueueCreate(BLOCK_COUNT, sizeof(uint8_t));
  readyClips = xQueueCreate(1, sizeof(AudioClip));
  bool allocated = freeBlocks && readyClips;
  for (uint8_t i = 0; i < BLOCK_COUNT && allocated; ++i) {
    audioBlocks[i] = static_cast<int16_t *>(malloc(BLOCK_BYTES));
    allocated = audioBlocks[i] != nullptr;
    if (allocated) xQueueSend(freeBlocks, &i, 0);
  }
  if (!allocated) {
    Serial.println("# ERROR: audio buffer allocation failed; reset board");
    while (true) delay(1000);
  }
  sessionId = esp_random();
  microphone.setPins(MIC_BCLK, MIC_WS, -1, MIC_SD);
  if (!microphone.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                        I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("# ERROR: microphone initialization failed; check wiring");
    while (true) delay(1000);
  }
  Serial.println("# Collar demo: continuous four-second WAVs; NO wake-word detection");
  if (xTaskCreatePinnedToCore(microphoneTask, "collarAudio", 4096, nullptr, 2, nullptr, 1) != pdPASS ||
      xTaskCreatePinnedToCore(networkTask, "collarNetwork", 6144, nullptr, 1, nullptr, 0) != pdPASS) {
    Serial.println("# ERROR: task allocation failed; reset board");
    while (true) delay(1000);
  }
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
