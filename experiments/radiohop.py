import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island.reports import build_report
from soundout.radio.channel import through_radio
from soundout.radio.link import receive, transmit
from soundout.radio.preamble import WAKE_GAP_MS, WAKE_MS, find_burst, wake
from soundout.radio.tones import MODES, RATE

RNG = np.random.default_rng(83)

REPORT = dict(reporter=1041, shelter=37, people=42, capacity=60,
              needs=["water", "insulin"], casualties=2, access="impassable",
              minutes=1_234_567)


def through(payload, snr_db, radio, mode="fast", vox_clip_ms=180):
    signal = transmit(payload, mode=mode, radio=radio)
    padded = np.concatenate([np.zeros(int(RATE * 0.2)), signal, np.zeros(int(RATE * 0.3))])
    heard = through_radio(padded, snr_db, RNG, vox_clip_ms=vox_clip_ms)

    return receive(heard), len(signal) / RATE


def vox_sweep(trials=30):
    payload = build_report(**REPORT)

    print("does the wake-up tone matter? (30 trials, 10 dB channel)")
    print(f"  the wake tone is {WAKE_MS} ms plus a {WAKE_GAP_MS} ms gap\n")
    print("  VOX eats   without wake   with wake")

    for eaten in (0, 60, 120, 180, 250, 350, 450, 550):
        without = sum(1 for _ in range(trials)
                      if through(payload, 10, False, vox_clip_ms=eaten)[0]["ok"])
        with_wake = sum(1 for _ in range(trials)
                        if through(payload, 10, True, vox_clip_ms=eaten)[0]["ok"])

        print(f"  {eaten:6d} ms   {without / trials:12.0%}   {with_wake / trials:9.0%}")


def noise_sweep(trials=30):
    payload = build_report(**REPORT)

    print("\nthrough a radio, with the wake tone, 180 ms eaten by VOX")
    print("  SNR dB" + "".join(f"{name:>11}" for name in MODES))

    for snr in (10, 5, 0, -5, -10, -14):
        row = f"  {snr:6d}"
        for mode in MODES:
            delivered = sum(1 for _ in range(trials)
                            if through(payload, snr, True, mode=mode)[0]["ok"])
            row += f"{delivered / trials:>10.0%} "
        print(row)


def false_sync(trials=40):
    """The wake tone must be ignorable, not merely harmless."""
    print("\nthe wake tone is not mistaken for a preamble")

    alone = np.concatenate([np.zeros(int(RATE * 0.2)), wake(RATE), np.zeros(int(RATE * 0.5))])
    claimed = sum(1 for _ in range(trials)
                  if receive(through_radio(alone, 10, RNG, vox_clip_ms=0))["burst"]["found"])
    print(f"  wake tone with no frame behind it: {claimed}/{trials} claimed a preamble")

    payload = build_report(**REPORT)
    plain = transmit(payload)
    with_wake = transmit(payload, radio=True)
    lead = len(with_wake) - len(plain)

    drift = find_burst(with_wake, rate=RATE)["data_start"] - lead \
        - find_burst(plain, rate=RATE)["data_start"]
    print(f"  sync lands {drift:+d} samples from where it does without the tone")


def crashes(trials=40):
    """A crack can raise a false alarm. It cannot take the sync from a real chirp.

    The matched filter adds the chirp up coherently over its whole length, while an
    impulse only accumulates as a square root, so even a crack several times louder
    than the signal loses the argument.
    """
    payload = build_report(**REPORT)
    print("\na static crash landing partway through the transmission")
    print("  crash is         sync stolen   delivered")

    for loudness in (0.0, 1.0, 4.0):
        stolen = delivered = 0

        for i in range(trials):
            signal = transmit(payload, radio=True)
            padded = np.concatenate([np.zeros(int(RATE * 0.2)), signal,
                                     np.zeros(int(RATE * 0.3))])
            heard = through_radio(padded, 8, RNG)

            if loudness:
                width = int(RATE * 0.008)
                at = int(len(heard) * (0.3 + 0.4 * (i % 5) / 5))
                heard[at:at + width] += RNG.normal(0.0, loudness, width)

            result = receive(heard)
            truth = int(RATE * 0.2) + len(wake(RATE))

            stolen += abs(result["burst"]["chirp_start"] - truth) > 400
            delivered += result["ok"]

        how = "absent" if not loudness else f"{loudness:.0f}x the signal"
        print(f"  {how:15s}  {stolen / trials:10.0%}   {delivered / trials:8.0%}")


def airtime():
    payload = build_report(**REPORT)
    print("\nwhat the wake tone costs")

    for mode in MODES:
        plain = len(transmit(payload, mode=mode)) / RATE
        radio = len(transmit(payload, mode=mode, radio=True)) / RATE
        print(f"  {mode:9s} {plain:5.2f} s -> {radio:5.2f} s  (+{radio - plain:.2f} s)")


if __name__ == "__main__":
    vox_sweep()
    noise_sweep()
    false_sync()
    crashes()
    airtime()
