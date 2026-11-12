# VisionBot — Project Log

Running record of every work session. The kid fills the "What we did" parts; keep it short and honest. Judges often ask for exactly this.

**Entry template:**

```
## YYYY-MM-DD — <session title>
**What we did:**
**What broke / how we fixed it:**
**Numbers we used:** (pixel→cm scale, tolerances, PWM)
**Photos:** (file names)
**Next:**
```

---

## 2026-11-12 — Planning day

**What we did:**
- Reviewed the project proposal (Readme.md) and confirmed the build approach.
- Inventoried hardware: ESP32, 2 BO motors + wheels + 1 caster, L298N 2A driver, 4×1.5V cells (6×NiMH 7.2V planned later), Logitech HD 1080p USB webcam, wires.
- Wrote the 2-day build plan: [plan-2day-build.md](plan-2day-build.md).

**Key decisions:**
1. Robot is untethered — ESP32 powered onboard (USB power bank now; L298N 5V-out with the 7.2V NiMH pack later). Laptop ↔ ESP32 over Wi-Fi (UDP); ESP32 creates its own hotspot, so no venue Wi-Fi needed.
2. Slow-and-simple controller: turn-in-place → drive straight → stop. PWM ~40%, angle tolerance 20°, stop tolerance 8 cm.

**Numbers we used:** (none yet — pixel→cm scale and heading calibration happen in Day 1, Block 4)

**Next:** scaffold `code/` — ArUco marker generator, detection test, Wi-Fi drive test, main navigation script, ESP32 firmware.
