#include <Arduino.h>

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, LOW);   // Turn the LED ON (active-low)
  delay(1000);                      // Wait for 1 second
  digitalWrite(LED_BUILTIN, HIGH);  // Turn the LED OFF
  delay(1000);                      // Wait for 1 second
}
