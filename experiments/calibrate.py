import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import transmit
from soundout.radio.preamble import find_burst
from soundout.radio.tones import RATE

RNG = np.random.default_rng(31)
PAYLOAD = b"\x00" * 16


def with_burst(snr_db):
    signal = transmit(PAYLOAD)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
    return through_simulated_channel(padded, snr_db, RNG)


def without_burst(seconds=4.0):
    return RNG.normal(0.0, 0.2, int(RATE * seconds))


def sweep(trials=40):
    print("detection statistics — burst present")
    print("  SNR dB   median PSR   worst PSR   median match")

    for snr in (20, 10, 0, -5, -10, -15, -20):
        psrs = []
        matches = []

        for _ in range(trials):
            found = find_burst(with_burst(snr))
            psrs.append(found["psr"])
            matches.append(found["match"])

        print(f"  {snr:6d}   {np.median(psrs):10.1f}   {min(psrs):9.1f}   {np.median(matches):12.3f}")

    print("\ndetection statistics — nothing but noise (false alarm risk)")
    psrs = [find_burst(without_burst())["psr"] for _ in range(trials)]
    print(f"  median PSR {np.median(psrs):.1f}, worst case {max(psrs):.1f} over {trials} trials")
    print(f"  a threshold must sit above {max(psrs):.1f} to never fire on silence")


def accuracy_at(threshold, trials=40):
    print(f"\nwith threshold PSR >= {threshold}")
    print("  SNR dB   found   sample error")

    for snr in (10, 0, -10, -15, -20):
        found = 0
        errors = []

        for _ in range(trials):
            signal = transmit(PAYLOAD)
            lead = np.zeros(int(RATE * 0.3))
            padded = np.concatenate([lead, signal, np.zeros(int(RATE * 0.3))])

            delay = []
            received = through_simulated_channel(padded, snr, RNG, delay)
            true_start = delay[0] + len(lead)

            burst = find_burst(received, min_psr=threshold)
            if burst["found"]:
                found += 1
                errors.append(abs(burst["chirp_start"] - true_start))

        median_error = f"{np.median(errors):.0f}" if errors else "-"
        print(f"  {snr:6d}   {found / trials:5.0%}   {median_error:>12}")

    false_alarms = sum(1 for _ in range(trials)
                       if find_burst(without_burst(), min_psr=threshold)["found"])
    print(f"  false alarms on pure noise: {false_alarms}/{trials}")


if __name__ == "__main__":
    sweep()
    accuracy_at(8.0)
