import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import numpy as np

from soundout.radio.link import transmit
from soundout.radio.tones import RATE
from soundout.island.reports import build_report
from soundout.island.situation import NEEDS, describe
from soundout.island import validate

def main():
    parser = argparse.ArgumentParser(description="compose and transmit a situation report")
    parser.add_argument("--reporter", type=int, default=1041)
    parser.add_argument("--shelter", type=int, required=True)
    parser.add_argument("--people", type=int, required=True)
    parser.add_argument("--capacity", type=int, default=100)
    parser.add_argument("--needs", type=str, default="",
                        help="comma separated: " + ", ".join(NEEDS))
    parser.add_argument("--casualties", type=int, default=0)
    parser.add_argument("--access", type=str, default="open")
    parser.add_argument("--amplitude", type=float, default=0.7)
    parser.add_argument("--wav", type=str, default=None)
    parser.add_argument("--out-device", type=int, default=None)
    parser.add_argument("--mode", type=str, default="fast",
                        help="fast, far or farthest - slower reaches further")
    parser.add_argument("--quiet", action="store_true", help="do not play, just build")
    args = parser.parse_args()

    try:
        reporter = validate.field(args.reporter, "reporter")
        shelter = validate.field(args.shelter, "shelter")
        people = validate.field(args.people, "occupancy")
        capacity = validate.field(args.capacity, "capacity")
        casualties = validate.field(args.casualties, "casualties")
        needs = validate.needs(args.needs)
        access = validate.access(args.access)
        amplitude = validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
        out_device = validate.audio_device(args.out_device, "output")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    if capacity and people > capacity * 4:
        print(f"warning: {people} people in {capacity} places looks like a typo")

    payload = build_report(reporter, shelter, people, capacity,
                           needs, casualties, access)

    signal = transmit(payload, amplitude=amplitude, mode=args.mode)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"report  : {describe(payload[:12])}")
    print(f"payload : {len(payload)} bytes ({payload.hex()})")
    print(f"mode    : {args.mode}")
    print(f"airtime : {len(signal) / RATE:.2f} s")

    if args.wav:
        from soundout.radio.wav import write_wav
        write_wav(args.wav, padded)
        print(f"wrote   : {args.wav}")

    if not args.quiet:
        import sounddevice as sd
        print("transmitting…")
        sd.play(padded, RATE, device=out_device, blocking=True)
        print("sent")


if __name__ == "__main__":
    main()
