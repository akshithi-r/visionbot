"""Timed-pulse bench test - proves the FIRMWARE owns the burst timing.

Wheels UP for this one (robot on a box, markers irrelevant). Join the
"VisionBot" Wi-Fi first, then from code/python/:

    python pulse_test.py            # default check sequence (below)
    python pulse_test.py L200 F300  # or run your own pulses

Default sequence and what it proves:
  1. S            - park everything, check the ACK round trip
  2. R150 + SILENCE - laptop sends NOTHING for 1.5 s. New firmware: wheels
                      stop after ~150 ms (on-board timer). OLD firmware:
                      wheels keep spinning until the 600 ms deadman - that
                      long spin means you forgot to flash the new firmware.
  3. K stream       - 1 s of keepalives. Wheels must NOT move: K feeds the
                      deadman/ACKs only, never the motors.
  4. S            - park again, all done.

The robot's serial monitor (9600 baud) should print "[pulse] R for 150 ms"
and "[pulse] done -> STOP" - the kid can read those out loud as proof.
"""

import socket
import sys
import time

ROBOT_IP = "192.168.4.1"   # standard ESP8266 hotspot address
PORT = 5005                # must match UDP_PORT in src/main.cpp


class Link:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))          # stable port so ACKs can come back
        self.sock.settimeout(0.4)
        self.seq = 0

    def _send(self, payload):
        self.seq += 1
        self.sock.sendto((f"{payload}#{self.seq}\n").encode(),
                         (ROBOT_IP, PORT))

    def cmd(self, payload):
        """Send one command, wait briefly for its ACK, report."""
        self._send(payload)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.4:
            try:
                data, _ = self.sock.recvfrom(64)
            except socket.timeout:
                break
            txt = data.decode(errors="ignore").strip()
            if txt[:1] == "A":
                ms = (time.monotonic() - t0) * 1000
                print(f"  sent {payload:<5} -> ACK ({ms:.0f} ms round trip)")
                return True
        print(f"  sent {payload:<5} -> NO ACK "
              "(robot off? not on VisionBot Wi-Fi?)")
        return False

    def quiet(self, payload):
        """Send without waiting - used for the K keepalive stream."""
        self._send(payload)


def main():
    link = Link()
    args = sys.argv[1:]
    print(f"Pulse bench test -> {ROBOT_IP}:{PORT}  (Ctrl+C quits)")
    if args:
        for a in args:
            if a[0] in "FBLR" and a[1:].isdigit() and 50 <= int(a[1:]) <= 2000:
                link.cmd(a)
                time.sleep(0.6)
                link.cmd("S")
            else:
                print(f"  skipping {a!r}: a pulse looks like R150 "
                      "(F/B/L/R + ms, 50-2000)")
        return

    print("\n1) park + link check")
    link.cmd("S")

    print("\n2) R150, then the laptop goes SILENT (watch the wheels)")
    print("   new firmware: stop after ~150 ms   old firmware: spins ~600 ms")
    link.cmd("R150")
    time.sleep(1.5)          # deliberately send NOTHING - the whole point
    link.cmd("S")

    print("\n3) 1 s of K keepalives (wheels must stay still)")
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        link.quiet("K")
        time.sleep(0.1)
    link.cmd("S")

    print("\n4) done - if step 2 stopped fast and step 3 never moved,")
    print("   the firmware owns the timing. Bench test PASSED.")


if __name__ == "__main__":
    main()
