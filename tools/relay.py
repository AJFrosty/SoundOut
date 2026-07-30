import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import queue
import time

import numpy as np
import sounddevice as sd

from soundout.island import relay, validate
from soundout.island.reports import ingest
from soundout.island.situation import describe
from soundout.island.store import Store
from soundout.radio.link import transmit
from soundout.radio.tones import RATE

from tools.receiver import BLOCK, LONGEST_FRAME_S, default_input

QUIET_FOR = 1.0


class Station:
    """Listens, remembers, and repeats — but never while anyone else is talking."""

    def __init__(self, store, args, rng):
        self.store = store
        self.args = args
        self.rng = rng
        self.speak_after = None
        self.sent = 0

    def waiting(self):
        return relay.pending(self.store, limit=self.args.batch,
                             include_unverified=self.args.trust_anything)

    def consider(self, quiet_since):
        """Decide whether this is the moment to repeat something.

        Two conditions, both necessary. The air has to have been quiet for a moment, so a
        transmission in progress is not stamped on. And the randomised wait has to have
        elapsed, so that stations which all heard the same report do not answer in chorus.
        """
        if quiet_since is None or time.monotonic() - quiet_since < QUIET_FOR:
            self.speak_after = None
            return None

        waiting = self.waiting()
        if not waiting:
            self.speak_after = None
            return None

        if self.speak_after is None:
            self.speak_after = time.monotonic() + relay.backoff(self.rng, self.args.spread)
            print(f"  {len(waiting)} to pass on, speaking in "
                  f"{self.speak_after - time.monotonic():.1f} s")
            return None

        return waiting[0] if time.monotonic() >= self.speak_after else None

    def repeat(self, row, stream):
        payload = relay.payload_of(row)
        signal = transmit(payload, amplitude=self.args.amplitude,
                          mode=self.args.mode, radio=self.args.radio)

        print(f"  repeating {describe(bytes.fromhex(row['raw']))}"
              f"  (urgency {relay.urgency(row)})")

        # deafen the station while it talks: it will hear its own transmission otherwise,
        # and a station that ingests its own voice is a station arguing with itself
        stream.stop()
        try:
            sd.play(signal, RATE, device=self.args.out_device, blocking=True)
        finally:
            stream.start()

        relay.mark_relayed(self.store, row)
        self.speak_after = None
        self.sent += 1


def main():
    parser = argparse.ArgumentParser(
        description="listen, remember, and pass on what others cannot reach the base with")
    parser.add_argument("--device", type=int, default=None, help="input")
    parser.add_argument("--out-device", type=int, default=None)
    parser.add_argument("--db", type=str, default="relay.db")
    parser.add_argument("--window", type=float, default=6.0)
    parser.add_argument("--spread", type=float, default=8.0,
                        help="seconds to spread repeats over, so stations do not collide")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--amplitude", type=float, default=0.7)
    parser.add_argument("--mode", type=str, default="fast")
    parser.add_argument("--radio", action="store_true",
                        help="lead each repeat with a VOX wake-up tone")
    parser.add_argument("--trust-anything", action="store_true",
                        help="also pass on reports whose tag did not verify")
    parser.add_argument("--listen-only", action="store_true",
                        help="behave as a plain receiver, for comparison")
    args = parser.parse_args()

    try:
        window_s = validate.seconds(args.window, "window", LONGEST_FRAME_S + 1.0, 60.0)
        spread = validate.seconds(args.spread, "spread", 0.0, 120.0)
        device = validate.audio_device(args.device, "input")
        validate.audio_device(args.out_device, "output")
        validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    args.spread = spread
    device = device if device is not None else default_input()

    store = Store(args.db)
    station = Station(store, args, np.random.default_rng())

    print(f"relay station on {sd.query_devices(device)['name']}")
    print("listening only — nothing will be repeated" if args.listen_only else
          f"repeats spread over {spread:.0f} s, worst reports first")
    print(f"writing to {args.db} — ctrl-c to stop\n")

    incoming = queue.Queue()
    stream = sd.InputStream(samplerate=RATE, channels=1, device=device, blocksize=BLOCK,
                            callback=lambda data, n, at, status: incoming.put(data[:, 0].copy()))

    buffer = np.zeros(0)
    window_samples = int(RATE * window_s)
    keep_samples = int(RATE * LONGEST_FRAME_S)
    quiet_since = time.monotonic()

    try:
        with stream:
            while True:
                block = incoming.get()
                buffer = np.concatenate([buffer, block])

                if float(np.abs(block).max()) > 0.02:
                    quiet_since = None
                elif quiet_since is None:
                    quiet_since = time.monotonic()

                while len(buffer) >= window_samples:
                    outcome = ingest(buffer[:window_samples], store)

                    if outcome["stored"]:
                        mark = "OK " if outcome["authentic"] else "!! "
                        note = "" if outcome["fresh"] else "  (already had this one)"
                        print(f"[{time.strftime('%H:%M:%S')}] {mark}"
                              f"{outcome['description']}{note}")
                        buffer = buffer[window_samples:]
                    else:
                        buffer = buffer[window_samples - keep_samples:]

                if not args.listen_only:
                    row = station.consider(quiet_since)
                    if row is not None:
                        station.repeat(row, stream)
                        buffer = np.zeros(0)
                        quiet_since = time.monotonic()

    except KeyboardInterrupt:
        summary = store.summary()
        print(f"\nstopped. heard {summary['observations']} observations from "
              f"{summary['shelters']} shelters; passed on {station.sent}.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
