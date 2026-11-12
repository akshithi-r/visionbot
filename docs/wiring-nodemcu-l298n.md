# Wiring Guide — NodeMCU (ESP-12E / ESP8266) + L298N + BO Motors

Everything connects directly. **No extra electronics needed** — no level shifter, no resistors, no capacitors. The L298N's inputs work fine with the NodeMCU's 3.3V signals.

> Replaces the earlier `wiring-esp30pin-l298n.md` — the board turned out to be a NodeMCU (ESP8266), not a 30-pin ESP32. The motor-test firmware lives at `code/bot-program/bot-code/` (PlatformIO, env `nodemcuv2`).

## What you need (shopping check)

| Item | Qty | Notes |
|---|---|---|
| Male-to-female jumper wires | 7 | 6 signals + 1 ground; part of any DuPont jumper kit |
| 4×AA battery holder | 1 | With or without its own switch — both wired below |
| Small on/off switch (only if the holder has none) | 1 | Any slide/toggle switch works |
| USB power bank + micro-USB cable | 1 | Powers the NodeMCU for now |
| Small screwdriver | 1 | For the L298N screw terminals |
| Wire strippers / scissors | 1 | Parent helps strip wire ends |

If your BO motor wires end in DuPont connectors instead of bare ends: either insert two male-male jumpers into the screw terminals, or (parent) cut and strip the ends.

## The two boards

**NodeMCU v2 (ESP-12E):** find each pin by its **printed label** (small white text). They don't sit in one neat column — check the label twice before plugging in.

```
 D1  ──► ENA   (left motor speed, PWM)
 D2  ──► ENB   (right motor speed, PWM)
 D5  ──► IN1   (left motor direction)
 D6  ──► IN2   (left motor direction)
 D7  ──► IN3   (right motor direction)
 D0  ──► IN4   (right motor direction)
 GND ──► GND   (common ground — MANDATORY)
```

Why these pins: D3, D4, D8 are boot-strapping pins (a motor driver wired there can stop the board from starting up), and D0 has no PWM — so D0 takes a plain direction pin.

**L298N board:**

```
 Jumper caps:
   ENA ●── remove cap (we PWM this pin)
   ENB ●── remove cap (we PWM this pin)
   5V  ●── keep cap ON (enables the onboard 5V regulator)

 Header (signal side):
   ENA  IN1  IN2  IN3  IN4  ENB

 Screw terminals (power side):   +12V   GND   5V
 Screw terminals (output side):  OUT1 OUT2 (left motor)
                                 OUT3 OUT4 (right motor)
```

## Connection table (the kid wires, the parent checks)

| # | NodeMCU pin | → | L298N pin | Wire colour suggestion |
|---|---|---|---|---|
| 1 | D1 | → | ENA | orange |
| 2 | D2 | → | ENB | orange |
| 3 | D5 | → | IN1 | yellow |
| 4 | D6 | → | IN2 | yellow |
| 5 | D7 | → | IN3 | green |
| 6 | D0 | → | IN4 | green |
| 7 | GND | → | GND | black — **never skip this one** |

| # | From | → | To |
|---|---|---|---|
| 8 | Left motor wires | → | OUT1 / OUT2 screw terminals |
| 9 | Right motor wires | → | OUT3 / OUT4 screw terminals |
| 10 | Battery pack (+) — see switch wiring below | → | +12V screw terminal |
| 11 | Battery pack (−) | → | GND screw terminal |
| 12 | Power bank | → | NodeMCU micro-USB socket |

Notes:

- **Which motor wire goes to OUT1 vs OUT2 doesn't matter yet** — if a wheel spins the wrong way in Block 2, swap that motor's two wires. That's the normal fix, expect it once.
- **Battery switch OFF while wiring.** Parent inspects before the first ON.

## Battery + switch wiring

**If the holder has its own switch** (slide on the holder):

```
holder (+) red  ──────────────► L298N +12V
holder (−) black ─────────────► L298N GND
```

**If you're adding a separate switch** — the switch just breaks the (+) wire, either leg is fine, no polarity:

```
holder (+) red  ──► [ switch ] ──► L298N +12V
holder (−) black ─────────────────► L298N GND
```

## Power plan

**Now (4×1.5V alkaline = 6V):**
- Battery → switch → L298N `+12V`/`GND` (drives the motors)
- Power bank → NodeMCU micro-USB (the L298N's 5V regulator is unreliable below 7V input, so we don't use it yet)
- Expect the wheels a bit slow: the L298N eats ~2V, so 6V cells give the motors ~4V. Normal. Never use a rectangular 9V battery — it can't supply motor current.

**Exhibition (6×NiMH = 7.2V):**
- Battery → L298N `+12V`/`GND`
- L298N `5V` terminal → NodeMCU `VIN` pin (one extra M-F wire; power bank comes off)
- Everything else unchanged

## First-power-on checklist

1. All jumper wires seated firmly (tug test each one), labels double-checked
2. ENA/ENB caps removed, 5V cap on
3. No bare wire touching at the screw terminals
4. Robot on a cup, wheels off the ground
5. Battery ON → power bank ON → only then run the motor test
6. If the NodeMCU randomly reboots mid-run: suspect the power bank auto-shutting-off at light load — tell us, there are fixes
