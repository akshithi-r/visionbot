#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

// VisionBot — Wi-Fi DRIVE TEST (Day 1, Block 3)
// Board: NodeMCU v2 (ESP8266)   ·   Wiring: docs/wiring-nodemcu-l298n.md
//
// The NodeMCU creates its own hotspot "VisionBot". The laptop joins it
// (the laptop loses internet while joined — expected) and runs
// code/python/drive_test.py: W/A/S/D drive, SPACE stop, +/- speed, ESC quit.
//
// Commands arrive over UDP 10x per second, each with a sequence number
// ("F#12", "R#13", "V400#14") and are ACKNOWLEDGED back to the sender
// ("A12") - bidirectional radio, so the laptop can tell a live link from
// a dead one. Plain commands without "#n" (drive_test.py) still work.
// If commands stop for 600 ms the robot stops BY ITSELF (deadman).

// ---- pins (same wiring as the motor test) ----
#define ENA D1   // left motor speed  (PWM)
#define ENB D2   // right motor speed (PWM)
#define IN1 D5   // left motor direction
#define IN2 D6   // left motor direction
#define IN3 D7   // right motor direction
#define IN4 D0   // right motor direction

// ---- Wi-Fi / radio ----
#define AP_SSID    "VisionBot"     // hotspot name (open, no password)
#define UDP_PORT   5005
#define DEADMAN_MS 600             // stop after this much radio silence

IPAddress apIP(192, 168, 4, 1);    // standard ESP8266 hotspot address

// ---- speed ----
// PWM range is 0–1023 (set in setup). 400 ≈ 40%, like the motor test.
int driveSpeed = 400;

WiFiUDP udp;
unsigned long lastCmdMs = 0;       // 0 = no command received yet
char lastState = 'S';              // for printing state changes only

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

void applyCommand(char cmd) {
  switch (cmd) {
    case 'F': drive( driveSpeed,  driveSpeed); break;
    case 'B': drive(-driveSpeed, -driveSpeed); break;
    case 'L': drive(-driveSpeed,  driveSpeed); break;  // spin in place
    case 'R': drive( driveSpeed, -driveSpeed); break;  // spin in place
    case 'S': motorsStop(); break;
    default:  return;                                 // ignore junk
  }
  if (cmd != lastState) {           // print only on change, not 10x/s spam
    Serial.printf("[robot] %c at %d%% (%d/1023)\n", cmd, driveSpeed * 100 / 1023, driveSpeed);
    lastState = cmd;
  }
}

void setup() {
  // Motors OFF before anything else.
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  motorsStop();

  analogWriteRange(1023);          // PWM 0–1023, so 400 ≈ 40%

  Serial.begin(9600);
  Serial.println();
  Serial.println(F("=== VisionBot Wi-Fi drive test — NodeMCU + L298N ==="));

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
  bool ok = WiFi.softAP(AP_SSID);  // open hotspot
  if (!ok) {
    Serial.println(F("FATAL: could not start hotspot — restart the board."));
    return;                        // motors stay off; loop() does nothing
  }
  udp.begin(UDP_PORT);

  Serial.printf("Hotspot : \"%s\" (open, no password)\n", AP_SSID);
  Serial.printf("Robot IP: %s  port %u\n", WiFi.softAPIP().toString().c_str(), UDP_PORT);
  Serial.printf("Deadman : robot self-stops after %d ms of silence\n", DEADMAN_MS);
  Serial.println(F("On the laptop: join Wi-Fi \"VisionBot\", then run drive_test.py"));
  Serial.println(F("Pins: ENA=D1 ENB=D2 IN1=D5 IN2=D6 IN3=D7 IN4=D0"));
  Serial.println();
}

void loop() {
  // ---- receive commands ----
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buf[24];
    int n = udp.read(buf, sizeof(buf) - 1);
    if (n > 0) {
      buf[n] = 0;                    // zero-terminate
      long seq = -1;
      char *hash = strchr(buf, '#'); // optional "#seq" suffix
      if (hash) {
        seq = atol(hash + 1);
        *hash = 0;                   // strip it, leaving the bare command
      }
      if (buf[0] == 'V') {           // "V412" = set speed
        int v = atoi(buf + 1);
        driveSpeed = constrain(v, 0, 1023);
        applyCommand(lastState);     // re-apply current move at the new speed
        Serial.printf("[speed] %d/1023 (%d%%)\n", driveSpeed, driveSpeed * 100 / 1023);
      } else {
        applyCommand(buf[0]);        // F B L R S
      }
      if (seq >= 0) {                // acknowledge back to the sender
        char ack[12];
        int al = snprintf(ack, sizeof(ack), "A%ld", seq);
        udp.beginPacket(udp.remoteIP(), udp.remotePort());
        udp.write((const uint8_t *)ack, al);
        udp.endPacket();
      }
    }
    lastCmdMs = millis();
  }

  // ---- deadman: no news = stop ----
  if (lastCmdMs != 0 && millis() - lastCmdMs > DEADMAN_MS) {
    if (lastState != 'S') {
      Serial.println(F("[deadman] no commands for 600 ms -> STOP"));
    }
    motorsStop();
    lastState = 'S';
    lastCmdMs = 0;                 // don't retrigger every loop
  }
}
