import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island.reports import build_report
from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import receive, transmit
from soundout.radio.tones import RATE

RNG = np.random.default_rng(53)

REPORT = dict(reporter=1041, shelter=37, people=42, capacity=60,
              needs=["water", "insulin"], casualties=2, access="impassable",
              minutes=1_234_567)


def deliver(payload, snr_db, parity):
    signal = transmit(payload, parity_bytes=parity)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
    heard = through_simulated_channel(padded, snr_db, RNG)

    return receive(heard, parity_bytes=parity), len(signal) / RATE


def sweep(trials=40):
    payload = build_report(**REPORT)

    print("delivery of a 16-byte authenticated report, 40 trials per level")
    print("  parity bytes:        0 (crc only)      6 (corrects 3)     10 (corrects 5)")
    print("  SNR dB     delivered  repaired   delivered  repaired   delivered  repaired")

    for snr in (-10, -13, -15, -16, -17, -18, -20):
        row = f"  {snr:6d}  "

        for parity in (0, 6, 10):
            delivered = 0
            repairs = []

            for _ in range(trials):
                result, _ = deliver(payload, snr, parity)
                if result["ok"] and result["payload"] == payload:
                    delivered += 1
                    repairs.append(result.get("corrected", 0))

            average = f"{np.mean(repairs):.1f}" if repairs else "-"
            row += f"  {delivered / trials:8.0%}  {average:>8}  "

        print(row)


def airtime_table():
    payload = build_report(**REPORT)
    print("\nwhat each level of protection costs")
    print("  parity   airtime   corrects")

    for parity in (0, 4, 6, 8, 10):
        _, airtime = deliver(payload, 40, parity)
        print(f"  {parity:6d}   {airtime:5.2f} s   {parity // 2} damaged bytes")


def wrong_answers(trials=200, parity=6):
    print(f"\ncould a repaired frame ever be wrong? ({trials} trials at -18 dB)")
    payload = build_report(**REPORT)
    wrong = 0
    delivered = 0

    for _ in range(trials):
        result, _ = deliver(payload, -18, parity)
        if result["ok"]:
            if result["payload"] == payload:
                delivered += 1
            else:
                wrong += 1

    print(f"  delivered correct : {delivered}")
    print(f"  accepted but WRONG: {wrong}")
    print(f"  the crc sits underneath reed-solomon precisely to catch this")


if __name__ == "__main__":
    sweep()
    airtime_table()
    wrong_answers()
