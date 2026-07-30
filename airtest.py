import argparse

import numpy as np
import sounddevice as sd

from goertzel import RATE
from message import receive, transmit
from situation import REPORT_BYTES, describe, encode_report
from trust import ShelterKeys, tag

REPORT = dict(
    reporter=1041, shelter=37, occupancy=42, capacity=60,
    needs=["water", "insulin"], casualties=2, access="impassable", minutes=1_234_567,
)


def same_api_pair(preferred_output="speakers"):
    devices = sd.query_devices()
    apis = sd.query_hostapis()

    best = None
    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        for j, o in enumerate(devices):
            if o["max_output_channels"] < 1 or o["hostapi"] != d["hostapi"]:
                continue
            score = (preferred_output in o["name"].lower(), apis[d["hostapi"]]["name"] == "MME")
            if best is None or score > best[0]:
                best = (score, i, j)

    if best is None:
        raise SystemExit("no input and output on the same host API")

    return best[1], best[2]


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

    auto_in, auto_out = same_api_pair()
    in_device = args.in_device if args.in_device is not None else auto_in
    out_device = args.out_device if args.out_device is not None else auto_out

    if args.text:
        payload = args.text.encode("utf-8")
        expect = args.text
    else:
        keys = ShelterKeys()
        keys.issue(REPORT["reporter"])
        packed = encode_report(**REPORT)
        payload = packed + tag(packed, keys.get(REPORT["reporter"]))
        expect = describe(packed)

    outcome = run(payload, in_device, out_device, args.amplitude)

    if isinstance(outcome, tuple):
        heard, result = outcome
        if args.wav:
            from play import write_wav
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
