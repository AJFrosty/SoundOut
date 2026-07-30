import argparse
import numpy as np

from soundout.radio.link import transmit
from soundout.radio.tones import RATE
from soundout.island.reports import build_report
from soundout.island.situation import NEEDS, describe

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
    payload = build_report(args.reporter, args.shelter, args.people, args.capacity,
                           needs, args.casualties, args.access)

    signal = transmit(payload, amplitude=args.amplitude)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"report  : {describe(payload[:12])}")
    print(f"payload : {len(payload)} bytes ({payload.hex()})")
    print(f"airtime : {len(signal) / RATE:.2f} s")

    if args.wav:
        from soundout.radio.wav import write_wav
        write_wav(args.wav, padded)
        print(f"wrote   : {args.wav}")

    if not args.quiet:
        import sounddevice as sd
        print("transmitting…")
        sd.play(padded, RATE, device=args.out_device, blocking=True)
        print("sent")


if __name__ == "__main__":
    main()
