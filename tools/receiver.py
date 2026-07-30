import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import time

import numpy as np
import sounddevice as sd

from soundout.island.reports import ingest
from soundout.island.situation import describe
from soundout.island.store import Store
from soundout.island import validate
from soundout.radio.tones import RATE


def pick_input():
    devices = sd.query_devices()
    inputs = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    if not inputs:
        raise SystemExit("no input device — plug in a microphone or enable Stereo Mix")
    return inputs[0]


def handle(signal, store, verbose):
    outcome = ingest(signal, store)

    if not outcome["stored"]:
        if verbose and outcome["burst"]["found"]:
            print(f"  heard a preamble but lost the data: {outcome['reason']}")
        return False

    stamp = time.strftime("%H:%M:%S")
    mark = "OK " if outcome["authentic"] else "!! "
    note = "" if outcome["fresh"] else "  (already had this one)"
    print(f"[{stamp}] {mark}{outcome['description']}{note}")

    if not outcome["authentic"]:
        print("        authentication FAILED - stored but not trusted")

    return True


def main():
    parser = argparse.ArgumentParser(description="listen continuously and build the picture")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--db", type=str, default="soundout.db")
    parser.add_argument("--chunk", type=float, default=6.0)
    parser.add_argument("--overlap", type=float, default=2.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    try:
        chunk = validate.seconds(args.chunk, "chunk", 1.0, 60.0)
        overlap = validate.seconds(args.overlap, "overlap", 0.0, 30.0)
        chosen = validate.audio_device(args.device, "input")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    if overlap >= chunk:
        raise SystemExit(f"error: overlap ({overlap}s) must be shorter than chunk ({chunk}s)")

    device = chosen if chosen is not None else pick_input()
    store = Store(args.db)

    print(f"listening on {sd.query_devices(device)['name']}")
    print(f"writing to {args.db} — ctrl-c to stop\n")

    tail = np.zeros(0)
    frames = int(RATE * chunk)
    keep = int(RATE * overlap)

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
