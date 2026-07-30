import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import threading
import time

import numpy as np
import sounddevice as sd

from soundout.radio.channel import through_simulated_channel
from soundout.radio.preamble import find_start_by_energy as find_start
from soundout.radio.tones import RATE, SYMBOL_MS, TONES, decode, encode, symbol_length

LEAD_IN_S = 0.4
TAIL_S = 0.4


def pick_input(preferred="stereo mix"):
    devices = sd.query_devices()
    inputs = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

    if not inputs:
        raise SystemExit("no input device found - plug in a microphone, or enable Stereo Mix")

    for i, d in inputs:
        if preferred in d["name"].lower():
            return i

    return inputs[0][0]



def run(count, in_device, out_device, amplitude, simulate_snr=None, oracle_sync=False):
    rng = np.random.default_rng()
    sent = rng.integers(0, len(TONES), count)

    signal = encode(list(sent), amplitude=amplitude)
    padded = np.concatenate([
        np.zeros(int(RATE * LEAD_IN_S)),
        signal,
        np.zeros(int(RATE * TAIL_S)),
    ])

    print(f"sending {count} symbols at {1000 / SYMBOL_MS:.0f} baud "
          f"({2 * 1000 / SYMBOL_MS:.0f} bps), amplitude {amplitude}")

    true_delay = []

    if simulate_snr is not None:
        print(f"channel: simulated (random delay, gain, smoothing, clipping, {simulate_snr} dB SNR)")
        recorded = through_simulated_channel(padded, simulate_snr, rng, true_delay)
    else:
        if out_device is None:
            out_device = sd.default.device[1]

        print(f"in  : {sd.query_devices(in_device)['name']}")
        print(f"out : {sd.query_devices(out_device)['name']}")

        with_tail = np.concatenate([padded, np.zeros(int(RATE * 0.5))])
        captured = sd.playrec(
            with_tail, samplerate=RATE, channels=1, device=(in_device, out_device))
        sd.wait()

        recorded = captured.flatten().astype(np.float64)
    peak = np.abs(recorded).max()
    if peak > 0:
        recorded = recorded / peak * amplitude

    if oracle_sync and true_delay:
        start = true_delay[0] + int(RATE * LEAD_IN_S)
        print("sync   : ORACLE (true offset handed to the decoder)")
    else:
        start = find_start(recorded)
        print("sync   : energy threshold")

    n = symbol_length()
    window = recorded[start:start + n * count]

    if len(window) < n * count:
        raise SystemExit("recording ended early - increase TAIL_S")

    got = [s for s, _ in decode(window)]
    margins = [m for _, m in decode(window)]

    errors = sum(1 for a, b in zip(sent, got) if a != b)
    print(f"\nstart detected at sample {start} ({start / RATE * 1000:.0f} ms)")
    print(f"sent   : {''.join(str(s) for s in sent)}")
    print(f"got    : {''.join(str(s) for s in got)}")
    print(f"errors : {errors}/{count}  ({errors / count:.1%})")
    print(f"median detection margin: {np.median(margins):.1f}x over the runner-up")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=32)
    parser.add_argument("--in-device", type=int, default=None)
    parser.add_argument("--out-device", type=int, default=None)
    parser.add_argument("--amplitude", type=float, default=0.5)
    parser.add_argument("--oracle-sync", action="store_true",
                        help="decode from the true offset, to separate sync failures "
                             "from detection failures")
    parser.add_argument("--simulate", type=float, default=None,
                        help="skip the sound card, push the signal through a simulated "
                             "channel at this SNR in dB")
    args = parser.parse_args()

    run(
        args.symbols,
        None if args.simulate is not None
        else (args.in_device if args.in_device is not None else pick_input()),
        args.out_device,
        args.amplitude,
        args.simulate,
        args.oracle_sync,
    )
