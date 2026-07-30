import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import math

import numpy as np
import sounddevice as sd

from soundout.island import validate
from soundout.radio.devices import name_of, same_api_pair
from soundout.radio.tones import MODES, RATE, TONES, bin_spacing, goertzel_amplitude, tone

SPACING = 200
TONE_COUNT = 4


def measure(freq, in_device, out_device, amplitude, hold_ms=180):
    samples = int(RATE * hold_ms / 1000)
    lead = int(RATE * 0.05)

    played = np.concatenate([np.zeros(lead), tone(freq, samples, RATE, amplitude),
                             np.zeros(lead)])

    captured = sd.playrec(played, samplerate=RATE, channels=1,
                          device=(in_device, out_device))
    sd.wait()

    heard = captured.flatten().astype(np.float64)
    middle = heard[lead + samples // 4: lead + samples]

    if len(middle) < 256:
        return 0.0

    return goertzel_amplitude(middle, freq, RATE)


def to_decibels(value, reference):
    if value <= 0 or reference <= 0:
        return -99.0
    return 20 * math.log10(value / reference)


def best_tone_set(measured, spacing=SPACING, count=TONE_COUNT):
    frequencies = sorted(measured)
    best = None

    for start in frequencies:
        wanted = [start + i * spacing for i in range(count)]
        if any(f not in measured for f in wanted):
            continue

        if not all(all(abs(f / bin_spacing(RATE, s["symbol_ms"])
                           - round(f / bin_spacing(RATE, s["symbol_ms"]))) < 1e-9
                       for f in wanted)
                   for s in MODES.values()):
            continue

        weakest = min(measured[f] for f in wanted)
        if best is None or weakest > best[0]:
            best = (weakest, wanted)

    return best


def main():
    parser = argparse.ArgumentParser(
        description="measure what your speaker and microphone are actually good at")
    parser.add_argument("--low", type=int, default=400)
    parser.add_argument("--high", type=int, default=3600)
    parser.add_argument("--step", type=int, default=100)
    parser.add_argument("--amplitude", type=float, default=0.6)
    parser.add_argument("--in-device", type=int, default=None)
    parser.add_argument("--out-device", type=int, default=None)
    args = parser.parse_args()

    try:
        amplitude = validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
        validate.audio_device(args.in_device, "input")
        validate.audio_device(args.out_device, "output")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    auto_in, auto_out = same_api_pair()
    in_device = args.in_device if args.in_device is not None else auto_in
    out_device = args.out_device if args.out_device is not None else auto_out

    print(f"in  : {name_of(in_device)}")
    print(f"out : {name_of(out_device)}")
    print(f"sweeping {args.low}-{args.high} Hz in {args.step} Hz steps, "
          f"about {(args.high - args.low) // args.step * 0.3:.0f} s\n")

    frequencies = list(range(args.low, args.high + 1, args.step))
    measured = {f: measure(f, in_device, out_device, amplitude) for f in frequencies}

    loudest = max(measured.values())
    if loudest < 1e-4:
        raise SystemExit(
            "heard nothing at any frequency.\n"
            "Check the volume, and that the output is not muted or routed to headphones\n"
            "while the microphone is somewhere else. Run audiocheck to see the devices.")

    print("what came back, relative to the best frequency")
    for freq in frequencies:
        level = to_decibels(measured[freq], loudest)
        bar = "#" * max(int((level + 40) / 2), 0)
        mark = "  <- in use" if freq in TONES else ""
        print(f"  {freq:5d} Hz  {level:6.1f} dB  {bar}{mark}")

    current = min(measured[f] for f in TONES if f in measured) if \
        all(f in measured for f in TONES) else None
    best = best_tone_set(measured)

    print("\nrecommendation")
    if best is None:
        print("  could not fit four tones 200 Hz apart into the range measured")
        return

    weakest, chosen = best
    print(f"  best four tones 200 Hz apart : {chosen}")
    print(f"  weakest of those             : {to_decibels(weakest, loudest):.1f} dB")

    if current is not None:
        print(f"  weakest of the current set   : {to_decibels(current, loudest):.1f} dB")
        gain = to_decibels(weakest, current)
        print(f"  improvement                  : {gain:+.1f} dB "
              f"({2 ** (gain / 6):.1f}x the range)")

        if gain < 1.5:
            print("\n  the tones already sit close to the best part of the response;"
                  "\n  leave them alone.")
        else:
            print(f"\n  worth changing. In soundout/radio/tones.py set:"
                  f"\n      TONES = {chosen}")
            print("  then re-run this to confirm, and regenerate any saved wav files.")


if __name__ == "__main__":
    main()
