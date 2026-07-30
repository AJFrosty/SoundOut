import argparse
from datetime import datetime, timezone

import numpy as np

from goertzel import RATE
from message import transmit
from situation import NEEDS, describe, encode_report
from trust import derive_key, tag

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def minutes_now():
    return int((datetime.now(timezone.utc) - EPOCH).total_seconds() // 60)


def build(reporter, shelter, people, capacity, needs, casualties, access, minutes=None):
    packed = encode_report(
        reporter=reporter,
        shelter=shelter,
        occupancy=people,
        capacity=capacity,
        needs=needs,
        casualties=casualties,
        access=access,
        minutes=minutes if minutes is not None else minutes_now(),
    )
    return packed + tag(packed, derive_key(reporter))


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
    parser.add_argument("--quiet", action="store_true", help="do not play, just build")
    args = parser.parse_args()

    needs = [n.strip() for n in args.needs.split(",") if n.strip()]
    payload = build(args.reporter, args.shelter, args.people, args.capacity,
                    needs, args.casualties, args.access)

    signal = transmit(payload, amplitude=args.amplitude)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"report  : {describe(payload[:12])}")
    print(f"payload : {len(payload)} bytes ({payload.hex()})")
    print(f"airtime : {len(signal) / RATE:.2f} s")

    if args.wav:
        from play import write_wav
        write_wav(args.wav, padded)
        print(f"wrote   : {args.wav}")

    if not args.quiet:
        import sounddevice as sd
        print("transmitting…")
        sd.play(padded, RATE, device=args.out_device, blocking=True)
        print("sent")


if __name__ == "__main__":
    main()
