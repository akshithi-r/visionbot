#include <Arduino.h>

// VisionBot — MOTOR TEST (Day 1, Block 2)
// Board: NodeMCU v2 (ESP8266)   ·   Wiring: docs/wiring-nodemcu-l298n.md
//
// HOW TO RUN: robot ON A CUP, wheels off the ground, battery switch ON.
// Open the serial monitor (9600 baud) — it says what each wheel SHOULD do.
// A wheel spinning the wrong way is NORMAL on first try: swap that motor's
// two wires at the L298N screw terminals (OUT1/OUT2 = left, OUT3/OUT4 = right).
//
// FRONT of the robot = the caster-wheel end.

// ---- pins (match the wiring doc) ----
#define ENA D1   // left motor speed  (PWM)
#define ENB D2   // right motor speed (PWM)
#define IN1 D5   // left motor direction
#define IN2 D6   // left motor direction
#define IN3 D7   // right motor direction
#define IN4 D0   // right motor direction (D0 has no PWM — fine, it's only on/off)

// ---- speed ----
// We set the PWM range to 0–1023, so 400 ≈ 40% — slow and safe on purpose.
#define TEST_SPEED 400

void motorsStop() {
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

// left/right speed: -1023 (full back) .. +1023 (full fwd). 0 = motor off.
void drive(int leftSpeed, int rightSpeed) {
  digitalWrite(IN1, leftSpeed >= 0 ? HIGH : LOW);
  digitalWrite(IN2, leftSpeed <  0 ? HIGH : LOW);
  digitalWrite(IN3, rightSpeed >= 0 ? HIGH : LOW);
  digitalWrite(IN4, rightSpeed <  0 ? HIGH : LOW);
  analogWrite(ENA, abs(leftSpeed));
  analogWrite(ENB, abs(rightSpeed));
}

void forward()   { drive(  TEST_SPEED,  TEST_SPEED); }
void backward()  { drive( -TEST_SPEED, -TEST_SPEED); }
void turnLeft()  { drive( -TEST_SPEED,  TEST_SPEED); }  // spin in place
void turnRight() { drive(  TEST_SPEED, -TEST_SPEED); }  // spin in place

void setup() {
  // Motors OFF before anything else.
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  motorsStop();

  analogWriteRange(1023);   // PWM 0–1023, so 400 ≈ 40%

  Serial.begin(9600);
  Serial.println();
  Serial.println(F("=== VisionBot motor test — NodeMCU + L298N ==="));
  Serial.println(F("Pins: ENA=D1 ENB=D2 IN1=D5 IN2=D6 IN3=D7 IN4=D0"));
  Serial.println(F("Robot on a cup, wheels UP. FRONT = caster end."));
  Serial.println(F("Wrong-direction wheel? Swap that motor's wires at OUT1/2 or OUT3/4."));
  Serial.println();
}

void loop() {
  Serial.println(F("STOP     - everything still. Anything spinning now = wiring problem, power off."));
  motorsStop();
  delay(2000);

  Serial.println(F("FORWARD  - both wheels toward the FRONT."));
  forward();
  delay(2000);
  motorsStop();
  delay(1000);

  Serial.println(F("BACKWARD - both wheels toward the BACK."));
  backward();
  delay(2000);
  motorsStop();
  delay(1000);

  Serial.println(F("LEFT     - left wheel BACK, right wheel FRONT."));
  turnLeft();
  delay(2000);
  motorsStop();
  delay(1000);

  Serial.println(F("RIGHT    - left wheel FRONT, right wheel BACK."));
  turnRight();
  delay(2000);
  motorsStop();
  delay(1000);

  Serial.println(F("Cycle done - repeating. Flip the battery switch off when done."));
}
