// FireBeetle ESP32: thumb GPIO35, index GPIO34, middle GPIO39.
// Open Serial Monitor at 115200 baud. Bend each finger and watch its value.

const int THUMB_PIN = 35;
const int INDEX_PIN = 34;
const int MIDDLE_PIN = 39;

int readFlex(int pin) {
  analogRead(pin); // Discard the first reading after changing ADC channels.
  delayMicroseconds(200);
  int total = 0;
  for (int i = 0; i < 8; i++) total += analogRead(pin);
  return total / 8;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(THUMB_PIN, ADC_11db);
  analogSetPinAttenuation(INDEX_PIN, ADC_11db);
  analogSetPinAttenuation(MIDDLE_PIN, ADC_11db);
  pinMode(THUMB_PIN, INPUT);
  pinMode(INDEX_PIN, INPUT);
  pinMode(MIDDLE_PIN, INPUT);
}

void loop() {
  int thumb = readFlex(THUMB_PIN);
  int index = readFlex(INDEX_PIN);
  int middle = readFlex(MIDDLE_PIN);

  Serial.print("Thumb: "); Serial.print(thumb);
  Serial.print("  Index: "); Serial.print(index);
  Serial.print("  Middle: "); Serial.println(middle);
  delay(100);
}
