import argparse
import time

import numpy as np
import sounddevice as sd

from goertzel import RATE
from message import receive
from situation import REPORT_BYTES, decode_report, describe
from store import Store
from trust import TAG_BYTES, derive_key, verify_tag


def pick_input():
    devices = sd.query_devices()
    inputs = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not inputs:
        raise SystemExit("no input device — plug in a microphone or enable Stereo Mix")
    return inputs[0]


def authenticate(payload):
    if len(payload) != REPORT_BYTES + TAG_BYTES:
        return None, False, f"expected {REPORT_BYTES + TAG_BYTES} bytes, got {len(payload)}"

    body = payload[:REPORT_BYTES]
    received = payload[REPORT_BYTES:]
    reporter = decode_report(body)["reporter"]

    return body, verify_tag(body, received, derive_key(reporter)), None


def handle(signal, store, verbose):
    result = receive(signal)

    if not result["ok"]:
        if verbose and result["burst"]["found"]:
            print(f"  heard a preamble but lost the data: {result['error']}")
        return False

    body, authentic, error = authenticate(result["payload"])
    if error:
        print(f"  frame decoded but not a report: {error}")
        return False

    fresh = store.add(body, authenticated=authentic)
    fields = decode_report(body)

    stamp = time.strftime("%H:%M:%S")
    mark = "OK " if authentic else "!! "
    note = "" if fresh else "  (already had this one)"
    print(f"[{stamp}] {mark}{describe(fields)}{note}")

    if not authentic:
        print("        authentication FAILED — stored but not trusted")

    return True


def main():
    parser = argparse.ArgumentParser(description="listen continuously and build the picture")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--db", type=str, default="soundout.db")
    parser.add_argument("--chunk", type=float, default=6.0)
    parser.add_argument("--overlap", type=float, default=2.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    device = args.device if args.device is not None else pick_input()
    store = Store(args.db)

    print(f"listening on {sd.query_devices(device)['name']}")
    print(f"writing to {args.db} — ctrl-c to stop\n")

    tail = np.zeros(0)
    frames = int(RATE * args.chunk)
    keep = int(RATE * args.overlap)

    try:
        while True:
            block = sd.rec(frames, samplerate=RATE, channels=1,
                           device=device, blocking=True).flatten().astype(np.float64)

            window = np.concatenate([tail, block])
            if handle(window, store, args.verbose):
                tail = np.zeros(0)
            else:
                tail = window[-keep:] if len(window) > keep else window

    except KeyboardInterrupt:
        summary = store.summary()
        print(f"\nstopped. {summary['observations']} observations from "
              f"{summary['shelters']} shelters, {summary['people']} people sheltered.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
