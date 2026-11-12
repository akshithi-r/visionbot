"""VisionBot Wi-Fi drive test (Day 1, Block 3).

BEFORE running:
  1. Power the robot (battery ON, NodeMCU on the power bank).
  2. Join this laptop's Wi-Fi to the hotspot "VisionBot" (open, no password).
     The laptop loses internet while joined - that is expected.
  3. Then run this script (Windows and Linux both fine).

KEYS
  W / ArrowUp      forward          S / ArrowDown    backward
  A / ArrowLeft    spin left        D / ArrowRight   spin right
  SPACE            stop
  + / -            speed up / down  (ESC             stop + quit)

Commands go out 10x per second; if they stop, the robot stops itself after
0.6 s (deadman in the firmware) - try turning the laptop Wi-Fi off mid-drive.

If nothing moves: check the laptop is joined to "VisionBot" (not your home
Wi-Fi) and try `ping 192.168.4.1` in a terminal.

No extra installs needed - standard library only.
"""

import argparse
import contextlib
import socket
import sys
import time

if sys.platform == "win32":
    import msvcrt

    def get_key():
        """One key press ('w', ' ', '\\xe0H', '\\x1b', ...) or None."""
        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getwch()
        if ch in ("\xe0", "\x00"):        # arrow/function key prefix
            ch += msvcrt.getwch()         # + H/K/M/P etc.
        return ch

    KEY_TO_CMD = {
        "w": "F", "\xe0H": "F",           # up arrow
        "s": "B", "\xe0P": "B",           # down arrow
        "a": "L", "\xe0K": "L",           # left arrow
        "d": "R", "\xe0M": "R",           # right arrow
        " ": "S",
    }

    terminal = contextlib.nullcontext     # nothing to set up on Windows

else:  # Linux (the Ubuntu demo box)
    import select
    import termios
    import tty

    KEY_TO_CMD = {
        "w": "F", "\x1b[A": "F",          # up arrow
        "s": "B", "\x1b[B": "B",          # down arrow
        "a": "L", "\x1b[D": "L",          # left arrow
        "d": "R", "\x1b[C": "R",          # right arrow
        " ": "S",
    }

    class _CbreakTerminal:
        """Switch stdin to cbreak (key-by-key) and restore on exit."""

        def __enter__(self):
            self._old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin)
            return self

        def __exit__(self, *exc):
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old)

    terminal = _CbreakTerminal

    def get_key():
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":                  # ESC - or the start of an arrow key
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                return "\x1b"             # plain ESC
            return ch + sys.stdin.read(2)  # e.g. "\x1b[A" = up arrow
        return ch

ROBOT_IP = "192.168.4.1"   # standard ESP8266 hotspot address
PORT = 5005                # must match UDP_PORT in src/main.cpp
SEND_HZ = 10               # command rate (plan: 10 Hz)

CMD_NAME = {"F": "FORWARD", "B": "BACKWARD", "L": "LEFT", "R": "RIGHT", "S": "STOP"}

SPEED_STEP = 50
SPEED_MAX = 1023


def main():
    ap = argparse.ArgumentParser(description="Drive the VisionBot with W/A/S/D over Wi-Fi.")
    ap.add_argument("--ip", default=ROBOT_IP, help=f"robot IP (default {ROBOT_IP})")
    ap.add_argument("--port", type=int, default=PORT, help=f"UDP port (default {PORT})")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (args.ip, args.port)

    state = "S"      # F/B/L/R/S, what we would send right now
    speed = 400      # 0..1023, matches firmware default (approx 40%)
    sent = 0

    def send(msg):
        nonlocal sent
        sock.sendto((msg + "\n").encode(), addr)
        sent += 1

    print(f"=== VisionBot drive test -> {args.ip}:{args.port} ===")
    print("W fwd · S back · A left · D right · SPACE stop · +/- speed · ESC quit")
    print("(arrow keys work too. Ctrl+C also quits.)")

    send(f"V{speed}")   # make sure firmware speed matches what we show

    next_send = time.monotonic()
    with terminal():
        try:
            while True:
                # --- keyboard, ~100 Hz ---
                key = get_key()
                if key is not None:
                    if key == "\x1b":                    # ESC
                        break
                    elif key in ("+", "="):
                        speed = min(speed + SPEED_STEP, SPEED_MAX)
                        send(f"V{speed}")
                    elif key in ("-", "_"):
                        speed = max(speed - SPEED_STEP, 0)
                        send(f"V{speed}")
                    elif key in KEY_TO_CMD:
                        state = KEY_TO_CMD[key]
                    else:
                        state = "S"                      # unknown key = safest move

                # --- send at SEND_HZ, even if nothing changed (feeds the deadman) ---
                now = time.monotonic()
                if now >= next_send:
                    send(state)
                    next_send = now + 1.0 / SEND_HZ
                    print(f"\r{CMD_NAME[state]:<8} {speed * 100 // 1023:3d}%  sent={sent}   ",
                          end="", flush=True)

                time.sleep(0.01)
        except KeyboardInterrupt:
            pass

    # Quit safely: a burst of STOPs so the robot is parked even with packet loss.
    for _ in range(5):
        send("S")
        time.sleep(0.05)
    print("\nStopped and quit. You can power the robot off.")


if __name__ == "__main__":
    main()
