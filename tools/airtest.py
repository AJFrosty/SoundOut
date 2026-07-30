import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse

import numpy as np
import sounddevice as sd

from soundout.radio.devices import same_api_pair
from soundout.island.reports import build_report
from soundout.island.situation import REPORT_BYTES, describe
from soundout.radio.link import receive, transmit
from soundout.radio.tones import RATE
from soundout.island import validate

REPORT = dict(
    reporter=1041, shelter=37, people=42, capacity=60,
    needs=["water", "insulin"], casualties=2, access="impassable", minutes=1_234_567,
)



def run(payload, in_device, out_device, amplitude, lead_s=0.5, tail_s=0.8):
    signal = transmit(payload, amplitude=amplitude)
    padded = np.concatenate([
        np.zeros(int(RATE * lead_s)), signal, np.zeros(int(RATE * tail_s))])

    print(f"in  : {sd.query_devices(in_device)['name']}")
    print(f"out : {sd.query_devices(out_device)['name']}")
    print(f"sending {len(payload)} bytes, {len(signal) / RATE:.2f} s of audio")

    captured = sd.playrec(padded, samplerate=RATE, channels=1,
                          device=(in_device, out_device))
    sd.wait()

    heard = captured.flatten().astype(np.float64)
    peak = float(np.abs(heard).max())
    print(f"heard: peak {peak:.4f}", end="")

    if peak < 1e-4:
        print(" — SILENT, nothing reached the microphone")
        return None
    if peak > 0.98:
        print(" — clipping, lower the volume")
    else:
        print("")

    result = receive(heard)
    burst = result["burst"]
    print(f"sync : {'FOUND' if burst['found'] else 'not found'} "
          f"(PSR {burst['psr']:.1f} of 8.0 needed, match {burst['match']:.3f})")

    if not result["ok"]:
        print(f"fail : {result['error']}")
        return heard

    print(f"ok   : {len(result['payload'])} bytes recovered, "
          f"margin {result['median_margin']:.1f}x")
    return heard, result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-device", type=int, default=None)
    parser.add_argument("--out-device", type=int, default=None)
    parser.add_argument("--amplitude", type=float, default=0.5)
    parser.add_argument("--text", type=str, default=None)
    parser.add_argument("--wav", type=str, default=None)
    args = parser.parse_args()

    try:
        validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
        validate.audio_device(args.in_device, "input")
        validate.audio_device(args.out_device, "output")
    except validate.Invalid as error:
        raise SystemExit(f"error: {error}")

    auto_in, auto_out = same_api_pair()
    in_device = args.in_device if args.in_device is not None else auto_in
    out_device = args.out_device if args.out_device is not None else auto_out

    if args.text:
        payload = args.text.encode("utf-8")
        expect = args.text
    else:
        payload = build_report(**REPORT)
        expect = describe(payload[:REPORT_BYTES])

    outcome = run(payload, in_device, out_device, args.amplitude)

    if isinstance(outcome, tuple):
        heard, result = outcome
        if args.wav:
            from soundout.radio.wav import write_wav
            write_wav(args.wav, heard)
            print(f"saved: {args.wav}")

        body = result["payload"][:REPORT_BYTES]
        if args.text:
            print(f"text : \"{result['text']}\"")
            print(f"exact: {result['text'] == expect}")
        else:
            try:
                print(f"report: {describe(body)}")
                print(f"exact : {describe(body) == expect}")
            except ValueError:
                print("payload was not a valid report")
