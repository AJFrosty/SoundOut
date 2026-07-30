import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
import os

import numpy as np

from soundout.island import authority, validate
from soundout.island.reports import minutes_now, sign_broadcast
from soundout.island.store import Store
from soundout.island.trust import Authority
from soundout.radio.link import transmit
from soundout.radio.tones import RATE

COUNTER = ".broadcast-sequence"


def next_sequence():
    """Sequence numbers must not repeat, or a replay becomes indistinguishable from news.

    Kept beside the database rather than in it, because the office signing orders is not
    necessarily the machine holding the reports.
    """
    used = json.load(open(COUNTER))["sequence"] if os.path.exists(COUNTER) else 0
    following = (used + 1) % (1 << 9)
    json.dump({"sequence": following}, open(COUNTER, "w"))
    return following


def holdings_from(db):
    if not os.path.exists(db):
        raise SystemExit(f"error: no such database: {db}")

    store = Store(db)
    try:
        return [(row["shelter"], row["minutes"]) for row in store.view()]
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(
        description="send a signed order, or a digest of what the base already holds")
    parser.add_argument("--order", type=str, default=None,
                        help="one of: " + "; ".join(a for a in authority.ACTIONS
                                                    if a != "reserved"))
    parser.add_argument("--digest", action="store_true",
                        help="tell everyone what has arrived, so relays can stop repeating it")
    parser.add_argument("--db", type=str, default="soundout.db")
    parser.add_argument("--scope", type=str, default="everyone",
                        choices=authority.SCOPES)
    parser.add_argument("--target", type=int, default=0,
                        help="shelter or zone number, when the scope is not everyone")
    parser.add_argument("--within", type=int, default=63,
                        help="hours; leave unset for no deadline")
    parser.add_argument("--amplitude", type=float, default=0.7)
    parser.add_argument("--mode", type=str, default="fast")
    parser.add_argument("--radio", action="store_true")
    parser.add_argument("--wav", type=str, default=None)
    parser.add_argument("--out-device", type=int, default=None)
    parser.add_argument("--quiet", action="store_true", help="do not play, just build")
    args = parser.parse_args()

    if bool(args.order) == args.digest:
        raise SystemExit("error: choose exactly one of --order or --digest")

    try:
        amplitude = validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
        out_device = validate.audio_device(args.out_device, "output")
        target = validate.whole_number(args.target, "target", 4095)
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    if args.scope != "everyone" and not target:
        raise SystemExit(f"error: --scope {args.scope} needs a --target")

    office = Authority.demo()
    issued = minutes_now()
    sequence = next_sequence()

    if args.order:
        if args.order not in authority.ACTIONS or args.order == "reserved":
            raise SystemExit(f"error: unknown order {args.order!r}\n  choose from: " +
                             "; ".join(a for a in authority.ACTIONS if a != "reserved"))
        if not 0 <= args.within <= 63:
            raise SystemExit("error: --within must be between 0 and 63 hours")

        body = authority.encode_order(issued, sequence, args.order,
                                      scope=args.scope, target=target,
                                      within_hours=args.within)
    else:
        holdings = holdings_from(args.db)
        if not holdings:
            raise SystemExit(f"error: {args.db} holds nothing to acknowledge yet")
        body = authority.encode_digest(issued, sequence, holdings)

    payload = sign_broadcast(body, office)
    signal = transmit(payload, amplitude=amplitude, mode=args.mode, radio=args.radio)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"message : {authority.describe(authority.decode(body))}")
    print(f"signed  : {len(body)} bytes + {len(payload) - len(body)} byte signature")
    print(f"sequence: {sequence}, issued at minute {issued}")
    print(f"airtime : {len(signal) / RATE:.2f} s"
          f"{' (a report is 2.28 s)' if args.mode == 'fast' else ''}")
    print(f"key     : {office.public_bytes().hex()[:16]}... - receivers verify against this")

    if args.wav:
        from soundout.radio.wav import write_wav
        write_wav(args.wav, padded)
        print(f"wrote   : {args.wav}")

    if not args.quiet:
        import sounddevice as sd
        print("transmitting...")
        sd.play(padded, RATE, device=out_device, blocking=True)
        print("sent")


if __name__ == "__main__":
    main()
