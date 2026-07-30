import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import json
import os
import time

import numpy as np
import sounddevice as sd

from soundout.island import validate
from soundout.radio.link import decode_at, duration_seconds
from soundout.radio.preamble import chirp, find_burst
from soundout.radio.tones import MODES, RATE, TONES

LOG = "rangetest.json"


def listen(seconds, device):
    print(f"  listening for {seconds:.0f} s — transmit now, as many times as you like")
    captured = sd.rec(int(RATE * seconds), samplerate=RATE, channels=1,
                      device=device, blocking=True)
    return captured.flatten().astype(np.float64)


def scan(signal, min_psr=8.0, min_match=0.05):
    """Find every burst in a recording, and say what happened to each.

    A consumed burst is overwritten with noise of the same level rather than with
    silence: a block of exact zeros has no sidelobes, which sends the peak-to-sidelobe
    ratio to infinity and invents bursts that were never there.
    """
    remaining = signal.copy()
    floor = float(np.median(np.abs(signal))) or 1e-4
    rng = np.random.default_rng(0)
    events = []

    for _ in range(20):
        best = None

        for name, settings in MODES.items():
            template = chirp(RATE, settings["chirp_ms"])
            burst = find_burst(remaining, template=template, rate=RATE, min_psr=min_psr)

            if burst["found"] and burst["match"] >= min_match                     and (best is None or burst["psr"] > best[1]["psr"]):
                best = (name, burst, settings)

        if best is None:
            break

        name, burst, settings = best
        outcome = decode_at(remaining, burst, RATE, 6, settings["symbol_ms"], TONES)

        events.append({
            "mode": name,
            "psr": round(burst["psr"], 1),
            "match": round(burst["match"], 3),
            "decoded": bool(outcome["ok"]),
            "reason": None if outcome["ok"] else outcome.get("error"),
            "margin": round(outcome.get("median_margin", 0), 1) if outcome["ok"] else None,
        })

        # blank exactly this burst, not its neighbours: a fast frame is 2.3 s and a
        # farthest one is 9 s, so a fixed span would swallow the next transmission
        span = duration_seconds(16, RATE, name) + 0.4
        start = max(burst["chirp_start"], 0)
        finish = min(start + int(RATE * span), len(remaining))
        remaining[start:finish] = rng.normal(0.0, floor * 1.25, finish - start)

    return events


def measure(distance, seconds, device, note):
    signal = listen(seconds, device)

    peak = float(np.abs(signal).max())
    clipped = float(np.mean(np.abs(signal) > 0.98))
    events = scan(signal)

    heard = len(events)
    decoded = sum(1 for e in events if e["decoded"])

    print(f"\n  level      : peak {peak:.3f}"
          f"{'  CLIPPING' if clipped > 0.001 else ''}")
    print(f"  bursts heard: {heard}")
    print(f"  decoded     : {decoded}")

    if heard:
        print(f"  median PSR  : {np.median([e['psr'] for e in events]):.1f}  (needs 8.0)")
        for event in events:
            state = "decoded" if event["decoded"] else f"lost: {event['reason']}"
            print(f"    {event['mode']:9s} PSR {event['psr']:6.1f}  {state}")
    else:
        print("  nothing heard at all — the preamble never rose above the noise")

    record = {
        "distance": distance,
        "note": note,
        "peak": round(peak, 4),
        "clipped": round(clipped, 4),
        "heard": heard,
        "decoded": decoded,
        "median_psr": round(float(np.median([e["psr"] for e in events])), 1) if events else None,
        "events": events,
        "at": time.strftime("%Y-%m-%d %H:%M"),
    }

    history = json.load(open(LOG)) if os.path.exists(LOG) else []
    history.append(record)
    json.dump(history, open(LOG, "w"), indent=1)
    print(f"\n  saved to {LOG}")


def summary():
    if not os.path.exists(LOG):
        raise SystemExit(f"no measurements yet — run this at a few distances first")

    history = json.load(open(LOG))
    print(f"range measurements ({len(history)} runs)\n")
    print("  distance  note            heard  decoded  median PSR  peak")

    for record in sorted(history, key=lambda r: (r["note"], r["distance"])):
        psr = f"{record['median_psr']:.1f}" if record["median_psr"] else "-"
        print(f"  {record['distance']:>7} m  {record['note'][:14]:14s}  "
              f"{record['heard']:5d}  {record['decoded']:7d}  {psr:>10}  {record['peak']:.3f}")

    print("\n  PSR falls as you move away. Below about 8 the preamble stops being found,")
    print("  which is the point where nothing arrives at all. If PSR is healthy but")
    print("  frames still fail, the limit is the data rather than the preamble — try")
    print("  --mode farthest on the transmitter.")


def main():
    parser = argparse.ArgumentParser(
        description="measure how far this actually works, and what stops it")
    parser.add_argument("--distance", type=float, help="metres, for the log")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--note", type=str, default="quiet",
                        help="conditions, e.g. quiet, fan on, outdoors")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.summary:
        summary()
        return

    if args.distance is None:
        raise SystemExit("say how far away the transmitter is, e.g. --distance 2")

    try:
        seconds = validate.seconds(args.seconds, "seconds", 5.0, 300.0)
        device = validate.audio_device(args.device, "input")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    if device is None:
        device = sd.default.device[0]

    print(f"\n{args.distance} m, {args.note}, on {sd.query_devices(device)['name']}")
    measure(args.distance, seconds, device, args.note)


if __name__ == "__main__":
    main()
