import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import queue
import time

import numpy as np
import sounddevice as sd

from soundout.island import validate
from soundout.island.reports import ingest
from soundout.island.store import Store
from soundout.radio.tones import RATE

LONGEST_FRAME_S = 3.0
BLOCK = 4096


def default_input():
    configured = sd.default.device[0]
    devices = sd.query_devices()

    if configured is not None and 0 <= configured < len(devices) \
            and devices[configured]["max_input_channels"] > 0:
        return configured

    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            return index

    raise SystemExit("no input device — plug in a microphone or enable Stereo Mix")


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
    parser.add_argument("--window", type=float, default=6.0,
                        help="how much audio to examine at once")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="no level meter")
    args = parser.parse_args()

    try:
        window_s = validate.seconds(args.window, "window", LONGEST_FRAME_S + 1.0, 60.0)
        chosen = validate.audio_device(args.device, "input")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    device = chosen if chosen is not None else default_input()
    store = Store(args.db)

    window_samples = int(RATE * window_s)
    keep_samples = int(RATE * LONGEST_FRAME_S)

    print(f"listening on {sd.query_devices(device)['name']}")
    print(f"examining {window_s:.0f} s at a time, carrying {LONGEST_FRAME_S:.0f} s across")
    print(f"writing to {args.db} — ctrl-c to stop\n")

    incoming = queue.Queue()

    def capture(indata, frames, at, status):
        if status and args.verbose:
            print(f"  audio status: {status}")
        incoming.put(indata[:, 0].copy())

    buffer = np.zeros(0)
    loudest = 0.0
    last_meter = time.monotonic()

    try:
        with sd.InputStream(samplerate=RATE, channels=1, device=device,
                            blocksize=BLOCK, callback=capture):
            while True:
                buffer = np.concatenate([buffer, incoming.get()])
                loudest = max(loudest, float(np.abs(buffer[-BLOCK:]).max()))

                now = time.monotonic()
                if not args.quiet and now - last_meter >= 3.0:
                    bar = "#" * min(int(loudest * 40), 20)
                    if loudest < 1e-4:
                        state = "silent — is the right device selected?"
                    elif loudest > 0.98:
                        state = f"{bar}  CLIPPING — turn the volume down"
                    else:
                        state = bar
                    print(f"  [level {loudest:.4f}] {state}")
                    loudest = 0.0
                    last_meter = now

                while len(buffer) >= window_samples:
                    if handle(buffer[:window_samples], store, args.verbose):
                        buffer = buffer[window_samples:]
                    else:
                        buffer = buffer[window_samples - keep_samples:]

    except KeyboardInterrupt:
        summary = store.summary()
        print(f"\nstopped. {summary['observations']} observations from "
              f"{summary['shelters']} shelters, {summary['people']} people sheltered.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
