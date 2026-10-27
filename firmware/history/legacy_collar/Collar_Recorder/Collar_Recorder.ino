#include <Arduino.h>
#include <ESP_I2S.h>

// Temporary enrollment firmware for the separate DFR0478 collar microphone.
// INMP441: 3V3, GND, L/R->GND, SCK->14, WS->17, SD->16.
I2SClass mic;
int32_t raw[320];
int16_t pcm[320];
uint32_t crcByte(uint32_t crc, uint8_t b) {
  crc ^= b;
  for (int n = 0; n < 8; ++n) crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320U : 0);
  return crc;
}
void setup() {
  Serial.begin(921600);
  mic.setPins(14, 17, -1, 16);
  if (!mic.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT,
                 I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("ERROR: microphone initialization failed");
    while (true) delay(1000);
  }
}
void loop() {
  // Always drain DMA. A request begins on a fresh 20 ms block boundary.
  size_t bytes = mic.readBytes(reinterpret_cast<char *>(raw), sizeof(raw));
  if (!Serial.available()) return;
  if (Serial.read() != 'R') return;
  while (Serial.available()) Serial.read();
  Serial.println("MILO_PCM 16000 48000");
  uint32_t crc = 0xffffffffU;
  bool valid = true;
  for (int frame = 0; frame < 150; ++frame) {
    bytes = mic.readBytes(reinterpret_cast<char *>(raw), sizeof(raw));
    if (bytes != sizeof(raw)) valid = false;
    for (int i = 0; i < 320; ++i) {
      int32_t value = (i < int(bytes / 4)) ? (raw[i] >> 16) * 4 : 0;
      pcm[i] = constrain(value, -32768, 32767);
    }
    const uint8_t *data = reinterpret_cast<uint8_t *>(pcm);
    for (size_t i = 0; i < sizeof(pcm); ++i) crc = crcByte(crc, data[i]);
    Serial.write(data, sizeof(pcm));
  }
  Serial.printf("CRC %08lx %s\n", (unsigned long)(crc ^ 0xffffffffU), valid ? "OK" : "BAD_READ");
}
