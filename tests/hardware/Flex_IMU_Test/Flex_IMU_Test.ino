// FireBeetle ESP32: flex + MPU6050 test only. Serial Monitor: 115200 baud.
// Flex: thumb GPIO35, index GPIO34, middle GPIO39. I2C: SDA21, SCL22.
#include <Arduino.h>
#include <Wire.h>

const uint8_t FLEX_PINS[3] = {35, 34, 39};
const int BEND[3] = {1460, 1596, 3480};
const int RELEASE[3] = {1420, 1533, 3460};
const uint8_t IMU_ADDRESS = 0x68;
bool bent[3] = {};
bool imuReady = false;
uint32_t lastRetry = 0;

bool readRegisters(uint8_t reg, uint8_t *data, uint8_t count) {
  Wire.beginTransmission(IMU_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(IMU_ADDRESS, count) != count) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint8_t i = 0; i < count; ++i) data[i] = Wire.read();
  return true;
}

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(IMU_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool setupImu() {
  uint8_t who = 0, ranges[2] = {};
  return readRegisters(0x75, &who, 1) && who == 0x68 &&
         writeRegister(0x6B, 1) && writeRegister(0x6C, 0) &&
         writeRegister(0x1A, 4) && writeRegister(0x19, 4) &&
         writeRegister(0x1B, 0x18) && writeRegister(0x1C, 0x18) &&
         readRegisters(0x1B, ranges, 2) &&
         (ranges[0] & 0x18) == 0x18 && (ranges[1] & 0x18) == 0x18;
}

int readFlex(uint8_t pin) {
  analogRead(pin);
  delayMicroseconds(200);
  int total = 0;
  for (int i = 0; i < 8; ++i) total += analogRead(pin);
  return total / 8;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  for (uint8_t pin : FLEX_PINS) {
    pinMode(pin, INPUT);
    analogSetPinAttenuation(pin, ADC_11db);
  }
  Wire.begin(21, 22);
  Wire.setClock(100000);
  Wire.setTimeOut(15);
  delay(100);
  imuReady = setupImu();
  lastRetry = millis();
  Serial.println("Flex + IMU only. Flex: raw ADC/state (0=NOT_BENT, 1=BENT).");
  Serial.println("Acceleration: m/s^2 including gravity. Gyroscope: rad/s.");
  Serial.println(imuReady ? "MPU6050 OK" : "MPU6050 NOT FOUND / INIT FAILED; retrying every 2 s.");
}

void loop() {
  int flex[3];
  for (int i = 0; i < 3; ++i) {
    flex[i] = readFlex(FLEX_PINS[i]);
    bent[i] = bent[i] ? flex[i] > RELEASE[i] : flex[i] >= BEND[i];
  }
  Serial.printf("Thumb: %d/%d  Index: %d/%d  Middle: %d/%d",
                flex[0], int(bent[0]), flex[1], int(bent[1]), flex[2], int(bent[2]));
  for (int i = 0; i < 3; ++i) {
    if (flex[i] <= 20 || flex[i] >= 4075) Serial.printf("  FLEX%d_RAIL", i + 1);
  }

  if (!imuReady && uint32_t(millis() - lastRetry) >= 2000) {
    lastRetry = millis();
    imuReady = setupImu();
  }
  uint8_t data[14];
  if (imuReady && readRegisters(0x3B, data, sizeof(data))) {
    float axes[6];
    bool clipped = false;
    for (int i = 0; i < 6; ++i) {
      int offset = (i < 3 ? i : i + 1) * 2; // Skip temperature registers.
      int16_t raw = int16_t((uint16_t(data[offset]) << 8) | data[offset + 1]);
      if (abs(int(raw)) >= 32700) clipped = true;
      axes[i] = i < 3 ? raw * 9.80665f / 2048.0f : raw * 0.01745329252f / 16.4f;
    }
    Serial.printf("  ax: %.3f ay: %.3f az: %.3f  gx: %.3f gy: %.3f gz: %.3f%s\n",
                  axes[0], axes[1], axes[2], axes[3], axes[4], axes[5],
                  clipped ? "  IMU_CLIPPED" : "");
  } else {
    if (imuReady) lastRetry = millis();
    imuReady = false;
    Serial.println("  IMU ERROR (check power / SDA21 / SCL22)");
  }
  delay(100);
}
