import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import argparse
import glob
import importlib
import os

import numpy as np

MODULES = [
    "soundout.radio.tones", "soundout.radio.preamble", "soundout.radio.framing",
    "soundout.radio.reedsolomon", "soundout.radio.link", "soundout.radio.channel",
    "soundout.radio.wav", "soundout.radio.devices",
    "soundout.island.situation", "soundout.island.trust",
    "soundout.island.reports", "soundout.island.store", "soundout.island.validate",
    "tools.report", "tools.receiver", "tools.listen", "tools.dashboard",
    "tools.airtest", "tools.loopback", "tools.audiocheck",
]

PASS = "ok  "
FAIL = "FAIL"


def line(state, what, detail=""):
    print(f"  [{state}] {what}{'  ' + detail if detail else ''}")
    return state == PASS


def check_imports():
    print("every module loads")
    healthy = True
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as error:
            healthy = line(FAIL, name, str(error)) and healthy
    if healthy:
        line(PASS, f"all {len(MODULES)} modules import cleanly")
    return healthy


def check_pipeline():
    from soundout.island.reports import build_report, ingest
    from soundout.island.store import Store
    from soundout.radio.link import receive, transmit
    from soundout.radio.tones import RATE
    from soundout.radio.wav import read_wav, write_wav

    print("\na report survives every path")
    payload = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                           needs=["water", "insulin"], casualties=2,
                           access="impassable", minutes=1_234_567)

    signal = transmit(payload)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
    healthy = True

    result = receive(padded)
    healthy &= line(PASS if result["ok"] and result["payload"] == payload else FAIL,
                    "in memory", f"{len(signal) / RATE:.2f} s of audio")

    temporary = "_selfcheck.wav"
    write_wav(temporary, padded)
    loaded, rate = read_wav(temporary)
    result = receive(loaded, rate=rate)
    healthy &= line(PASS if result["ok"] and result["payload"] == payload else FAIL,
                    "through a wav file")

    store = Store()
    outcome = ingest(loaded, store)
    healthy &= line(PASS if outcome["stored"] and outcome["authentic"] else FAIL,
                    "decoded, authenticated and stored",
                    outcome.get("description", outcome.get("reason", "")))
    store.close()
    os.remove(temporary)

    return healthy


def check_noise():
    from soundout.island.reports import build_report
    from soundout.radio.channel import through_simulated_channel
    from soundout.radio.link import receive, transmit
    from soundout.radio.tones import RATE

    print("\nit still works through noise")
    rng = np.random.default_rng(3)
    payload = build_report(reporter=1041, shelter=12, people=180, capacity=180,
                           needs=["water"], casualties=0, access="open", minutes=1_000)

    healthy = True
    for snr in (0, -10):
        delivered = 0
        for _ in range(10):
            signal = transmit(payload)
            padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal,
                                     np.zeros(int(RATE * 0.3))])
            result = receive(through_simulated_channel(padded, snr, rng))
            if result["ok"] and result["payload"] == payload:
                delivered += 1

        healthy &= line(PASS if delivered >= 9 else FAIL,
                        f"{snr:+d} dB channel", f"{delivered}/10 delivered")

    return healthy


def check_stale_audio():
    from soundout.radio.link import receive
    from soundout.radio.wav import read_wav

    files = sorted(glob.glob("*.wav")) + sorted(glob.glob("../*.wav"))
    if not files:
        return True

    print("\nwav files lying around")
    stale = []

    for path in files:
        if path.startswith("_"):
            continue
        try:
            signal, rate = read_wav(path)
            result = receive(signal, rate=rate)
        except Exception as error:
            line(FAIL, path, str(error))
            continue

        if result["ok"]:
            line(PASS, path, "decodes with the current format")
        else:
            stale.append(path)
            line("old ", path, result["error"])

    if stale:
        print(f"\n  {len(stale)} file(s) predate a format change and can never decode now.")
        print("  Regenerate them:  python -m tools.report --shelter 37 --people 42 --wav report.wav --quiet")

    return True


def check_audio_devices():
    print("\naudio devices")
    try:
        import sounddevice as sd
    except Exception as error:
        return line(FAIL, "sounddevice unavailable", str(error))

    devices = sd.query_devices()
    inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    outputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_output_channels"] > 0]

    line(PASS if inputs else FAIL, f"{len(inputs)} input(s)",
         inputs[0][1] if inputs else "nothing can be heard")
    line(PASS if outputs else FAIL, f"{len(outputs)} output(s)",
         outputs[0][1] if outputs else "nothing can be played")

    if inputs:
        print(f"  default input is device {sd.default.device[0]}; "
              f"pass --device N to choose another")

    return bool(inputs and outputs)


def check_dependencies():
    print("dependencies")
    healthy = True

    for name, why in (("numpy", "the maths"),
                      ("sounddevice", "playing and recording audio"),
                      ("cryptography", "Ed25519 for authority broadcasts")):
        try:
            module = importlib.import_module(name)
            healthy = line(PASS, name, getattr(module, "__version__", "")) and healthy
        except Exception:
            healthy = line(FAIL, name, f"missing — needed for {why}") and healthy

    if not healthy:
        print("\n  install everything with:  pip install -r requirements.txt")

    return healthy


def main():
    parser = argparse.ArgumentParser(description="is everything wired up correctly?")
    parser.add_argument("--skip-audio", action="store_true")
    args = parser.parse_args()

    print("SoundOut self check\n")

    if not check_dependencies():
        raise SystemExit(1)

    print()
    results = [check_imports(), check_pipeline(), check_noise(), check_stale_audio()]

    if not args.skip_audio:
        results.append(check_audio_devices())

    print()
    if all(results):
        print("everything checks out.")
    else:
        print("something is wrong — see the FAIL lines above.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
