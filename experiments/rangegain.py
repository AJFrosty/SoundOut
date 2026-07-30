import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island.reports import build_report
from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import receive, transmit
from soundout.radio.tones import MODES, RATE, rate_bps

RNG = np.random.default_rng(61)

REPORT = dict(reporter=1041, shelter=37, people=42, capacity=60,
              needs=["water", "insulin"], casualties=2, access="impassable",
              minutes=1_234_567)


def deliver(payload, snr_db, mode):
    signal = transmit(payload, mode=mode)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
    heard = through_simulated_channel(padded, snr_db, RNG)

    return receive(heard, mode=mode), len(signal) / RATE


def floor_for(payload, mode, trials=25):
    for snr in range(-10, -32, -1):
        delivered = sum(1 for _ in range(trials)
                        if deliver(payload, snr, mode)[0]["ok"])
        if delivered < trials * 0.9:
            return snr + 1
    return -31


def sweep(trials=25):
    payload = build_report(**REPORT)

    print("delivery of a 16-byte authenticated report, 25 trials per level")
    header = "  SNR dB  " + "".join(f"{name:>11}" for name in MODES)
    print(header)
    print("          " + "".join(f"{rate_bps(s['symbol_ms']):>7.0f} bps"
                                 for s in MODES.values()))

    for snr in (-14, -16, -18, -20, -22, -24, -26):
        row = f"  {snr:6d}  "
        for name in MODES:
            delivered = sum(1 for _ in range(trials)
                            if deliver(payload, snr, name)[0]["ok"])
            row += f"{delivered / trials:>10.0%} "
        print(row)


def summary():
    payload = build_report(**REPORT)
    print("\nwhat each mode costs and buys")
    print("  mode        bps   airtime   works down to   gain    range")

    reference = None
    for name, settings in MODES.items():
        _, airtime = deliver(payload, 40, name)
        floor = floor_for(payload, name)

        if reference is None:
            reference = floor

        gain = reference - floor
        print(f"  {name:9s} {rate_bps(settings['symbol_ms']):4.0f}   {airtime:6.2f} s   "
              f"{floor:9d} dB   {gain:+4d} dB   {2 ** (gain / 6):4.1f}x")

    print("\n  sound falls about 6 dB each time the distance doubles, so every 6 dB")
    print("  of gain is roughly twice the range for the same speaker and room.")


if __name__ == "__main__":
    sweep()
    summary()
