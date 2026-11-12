# Wiring Guide — 30-pin ESP32 + L298N + BO Motors

Everything connects directly. **No extra electronics needed** — no level shifter, no resistors, no capacitors. The L298N's inputs work fine with the ESP32's 3.3V signals.

## What you need (shopping check)

| Item | Qty | Notes |
|---|---|---|
| Male-to-female jumper wires | 7 | 6 signals + 1 ground; part of any DuPont jumper kit |
| 4×AA battery holder with switch | 1 | Wires to the L298N screw terminals |
| USB power bank + cable | 1 | Powers the ESP32 for now (check plug: micro-USB or USB-C) |
| Small screwdriver | 1 | For the L298N screw terminals |
| Wire strippers / scissors | 1 | Parent helps strip wire ends |

If your BO motor wires end in DuPont connectors instead of bare ends: either insert two male-male jumpers into the screw terminals, or (parent) cut and strip the ends.

## The two boards

**30-pin ESP32 DevKit (right-hand column, top to bottom):**

```
 EN
 VP  (GPIO36)
 VN  (GPIO39)
 D34
 D35
 D32  ──► ENA   (left motor speed, PWM)
 D33  ──► ENB   (right motor speed, PWM)
 D25  ──► IN1   (left motor direction)
 D26  ──► IN2   (left motor direction)
 D27  ──► IN3   (right motor direction)
 D14  ──► IN4   (right motor direction)
 D12
 D13
 GND  ──► GND   (common ground — MANDATORY)
 VIN
```

All six signal pins sit on the same column — convenient, one neat bundle of wires across to the driver.

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

| # | ESP32 pin | → | L298N pin | Wire colour suggestion |
|---|---|---|---|---|
| 1 | D32 | → | ENA | orange |
| 2 | D33 | → | ENB | orange |
| 3 | D25 | → | IN1 | yellow |
| 4 | D26 | → | IN2 | yellow |
| 5 | D27 | → | IN3 | green |
| 6 | D14 | → | IN4 | green |
| 7 | GND | → | GND | black — **never skip this one** |

| # | From | → | To |
|---|---|---|---|
| 8 | Left motor wires | → | OUT1 / OUT2 screw terminals |
| 9 | Right motor wires | → | OUT3 / OUT4 screw terminals |
| 10 | Battery pack (+) | → | +12V screw terminal |
| 11 | Battery pack (−) | → | GND screw terminal |
| 12 | Power bank | → | ESP32 USB socket |

Notes:

- **Which motor wire goes to OUT1 vs OUT2 doesn't matter yet** — if a wheel spins the wrong way in Block 2, swap that motor's two wires. That's the normal fix, expect it once.
- GPIOs 0, 2, 5, 12, 15 are deliberately avoided (boot-strapping pins — wiring motors there can stop the ESP32 from starting up).
- Battery **switch OFF** while wiring. Parent inspects before the first ON.

## Power plan

**Now (4×1.5V = 6V):**
- Battery → L298N `+12V`/`GND` (drives the motors)
- Power bank → ESP32 USB (the L298N's 5V regulator is unreliable below 7V input, so we don't use it yet)

**Exhibition (6×NiMH = 7.2V):**
- Battery → L298N `+12V`/`GND`
- L298N `5V` terminal → ESP32 `VIN` pin (one extra M-F wire; power bank comes off)
- Everything else unchanged

## First-power-on checklist

1. All 7 jumpers seated firmly (tug test each one)
2. ENA/ENB caps removed, 5V cap on
3. No bare wire touching at the screw terminals
4. Robot on a cup, wheels off the ground
5. Battery ON → power bank ON → only then run the motor test
