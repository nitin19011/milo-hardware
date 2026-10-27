// Glove flex-sensor GPIO test for DFR0478 FireBeetle ESP32.
// Open Serial Monitor or Serial Plotter at 115200 baud.
// Keep the existing 3.3 V / flex-sensor / 47 kOhm divider wiring.
// Reports averaged 12-bit ADC readings only; no bend thresholds.

#include <Arduino.h>

const int THUMB_PIN = 35;   // A3
const int INDEX_PIN = 34;   // A2
const int MIDDLE_PIN = 39;  // A1

int readFlex(int pin) {
  // Discard one reading after switching channels, then allow settling.
  analogRead(pin);
  delayMicroseconds(200);

  uint32_t total = 0;
  for (int i = 0; i < 8; ++i) {
    total += analogRead(pin);
  }
  return total / 8;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(THUMB_PIN, INPUT);
  pinMode(INDEX_PIN, INPUT);
  pinMode(MIDDLE_PIN, INPUT);

  analogReadResolution(12);  // Raw range: 0 to 4095.
  analogSetPinAttenuation(THUMB_PIN, ADC_11db);
  analogSetPinAttenuation(INDEX_PIN, ADC_11db);
  analogSetPinAttenuation(MIDDLE_PIN, ADC_11db);
}

void loop() {
  int thumb = readFlex(THUMB_PIN);
  int index = readFlex(INDEX_PIN);
  int middle = readFlex(MIDDLE_PIN);

  // Labelled values work in both Serial Monitor and Serial Plotter.
  Serial.print("Thumb_GPIO35:");
  Serial.print(thumb);
  Serial.print("\tIndex_GPIO34:");
  Serial.print(index);
  Serial.print("\tMiddle_GPIO39:");
  Serial.println(middle);

  delay(100);  // Approximately 10 updates per second.
}
