import argparse

import numpy as np
import sounddevice as sd

from soundout.island.situation import REPORT_BYTES, describe
from soundout.island.trust import TAG_BYTES
from soundout.radio.link import receive
from soundout.radio.tones import RATE


def pick_input():
    devices = sd.query_devices()
    inputs = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

    if not inputs:
        raise SystemExit(
            "No input device at all.\n"
            "Enable Stereo Mix (Sound settings -> Recording -> show disabled devices)\n"
            "or plug in any headset, webcam or USB microphone."
        )

    for i, d in inputs:
        if "stereo mix" in d["name"].lower():
            return i

    return inputs[0][0]


def level_report(signal):
    peak = float(np.abs(signal).max())
    rms = float(np.sqrt(np.mean(signal ** 2)))

    if peak < 1e-5:
        verdict = "SILENT - the device is capturing nothing"
    elif peak < 0.01:
        verdict = "very quiet - move closer or raise the volume"
    elif peak > 0.98:
        verdict = "clipping - lower the volume"
    else:
        verdict = "healthy"

    return peak, rms, verdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--wav", type=str, default=None, help="save what was heard")
    parser.add_argument("--expect", type=str, default=None, help="compare against this text")
    args = parser.parse_args()

    device = args.device if args.device is not None else pick_input()
    print(f"device : {sd.query_devices(device)['name']}")
    print(f"listening for {args.seconds:.0f} s — play the burst now")

    frames = int(RATE * args.seconds)
    heard = sd.rec(frames, samplerate=RATE, channels=1, device=device, blocking=True)
    signal = heard.flatten().astype(np.float64)

    peak, rms, verdict = level_report(signal)
    print(f"level  : peak {peak:.4f}, rms {rms:.4f} — {verdict}")

    if args.wav:
        from soundout.radio.wav import write_wav
        write_wav(args.wav, signal)
        print(f"saved  : {args.wav}")

    result = receive(signal)
    burst = result["burst"]

    print(f"preamble: {'FOUND' if burst['found'] else 'not found'} "
          f"(PSR {burst['psr']:.1f}, needs 8.0 — match {burst['match']:.3f})")

    if not result["ok"]:
        print(f"result : {result['error']}")
        if burst["found"]:
            print("         the chirp was heard but the data did not survive")
        return

    payload = result["payload"]
    print(f"result : {len(payload)} bytes, margin {result['median_margin']:.1f}x")

    if len(payload) in (REPORT_BYTES, REPORT_BYTES + TAG_BYTES):
        try:
            print(f"report : {describe(payload[:REPORT_BYTES])}")
        except ValueError:
            print(f"text   : \"{result['text']}\"")
    else:
        print(f"text   : \"{result['text']}\"")

    if args.expect:
        print(f"match  : {'EXACT' if result['text'] == args.expect else 'DIFFERS'}")


if __name__ == "__main__":
    main()
