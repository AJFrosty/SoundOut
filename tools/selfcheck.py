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
    "soundout.island.relay", "soundout.island.authority",
    "tools.report", "tools.receiver", "tools.listen", "tools.dashboard",
    "tools.airtest", "tools.loopback", "tools.audiocheck", "tools.relay", "tools.broadcast",
    "experiments.comparison", "experiments.chart", "experiments.authoritytest",
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


def check_relay():
    from soundout.island import relay
    from soundout.island.reports import build_report, ingest
    from soundout.island.store import Store
    from soundout.radio.link import transmit
    from soundout.radio.tones import RATE

    print("\na report survives being passed on")
    original = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                            needs=["insulin"], casualties=2, access="impassable",
                            minutes=1_234_567)

    def over_air(payload, store):
        signal = transmit(payload)
        return ingest(np.concatenate([np.zeros(int(RATE * 0.3)), signal,
                                      np.zeros(int(RATE * 0.3))]), store)

    middle, base = Store(), Store()
    healthy = True

    healthy &= line(PASS if over_air(original, middle)["authentic"] else FAIL,
                    "a station hears it")

    waiting = relay.pending(middle)
    healthy &= line(PASS if len(waiting) == 1 else FAIL,
                    "it is queued to pass on", f"{len(waiting)} waiting")

    if waiting:
        healthy &= line(PASS if relay.payload_of(waiting[0]) == original else FAIL,
                        "repeated byte for byte, tag included")

        arrived = over_air(relay.payload_of(waiting[0]), base)
        healthy &= line(PASS if arrived["authentic"] else FAIL,
                        "the base still trusts the original reporter")

        relay.mark_relayed(middle, waiting[0])
        healthy &= line(PASS if not relay.pending(middle) else FAIL,
                        "each station repeats it once", "which is what makes it stop")

    middle.close()
    base.close()
    return healthy


def check_authority():
    from soundout.island import authority
    from soundout.island.reports import ingest, sign_broadcast
    from soundout.island.trust import Authority
    from soundout.radio.link import transmit
    from soundout.radio.tones import RATE

    print("\norders from the base cannot be forged or replayed")
    office, impostor = Authority.demo(), Authority()
    issued = 500_000

    def over_air(payload, bulletin):
        signal = transmit(payload)
        return ingest(np.concatenate([np.zeros(int(RATE * 0.3)), signal,
                                      np.zeros(int(RATE * 0.3))]), None, bulletin=bulletin)

    def fresh():
        return authority.Bulletin(office.public_bytes(), now_minutes=issued)

    body = authority.encode_order(issued, 3, "evacuate now", scope="zone", target=3)
    genuine = sign_broadcast(body, office)
    healthy = True

    outcome = over_air(genuine, fresh())
    healthy &= line(PASS if "message" in outcome else FAIL,
                    "a genuine order arrives", outcome.get("description", ""))

    outcome = over_air(sign_broadcast(body, impostor), fresh())
    healthy &= line(PASS if "message" not in outcome else FAIL,
                    "one signed by somebody else is refused")

    altered = bytearray(genuine)
    altered[6] ^= 0x01
    outcome = over_air(bytes(altered), fresh())
    healthy &= line(PASS if "message" not in outcome else FAIL,
                    "one altered after signing is refused")

    listener = fresh()
    over_air(genuine, listener)
    outcome = over_air(genuine, listener)
    healthy &= line(PASS if "message" not in outcome else FAIL,
                    "a recording played again is refused")

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


def check_field_page():
    import re

    from soundout.island.situation import ACCESS, NEEDS, encode_report
    from soundout.island.trust import derive_key, tag
    from soundout.radio.framing import build_frame

    page = _Path(__file__).resolve().parents[1] / "field.html"
    print("\nfield.html agrees with this build")

    if not page.exists():
        return line(FAIL, "field.html is missing")

    html = page.read_text(encoding="utf-8")

    report = encode_report(
        reporter=1041, shelter=37, occupancy=42, capacity=60,
        needs=["water", "insulin"], casualties=2, access="impassable",
        minutes=1_234_567)

    key = derive_key(1041)
    payload = report + tag(report, key)

    expected = {
        "report": report.hex(),
        "key": key.hex(),
        "tag": tag(report, key).hex(),
        "frame": build_frame(payload).hex(),
    }

    healthy = True
    for name, value in expected.items():
        found = re.search(name + r':"([0-9a-f]+)"', html)

        if not found:
            healthy = line(FAIL, f"{name} vector missing from the page") and healthy
        elif found.group(1) != value:
            healthy = line(FAIL, f"{name} vector is stale",
                           "the page will build frames this build cannot read") and healthy
        else:
            healthy = line(PASS, f"{name} vector matches") and healthy

    from soundout.radio import preamble

    for name, constant, scale in (("WAKE", preamble.WAKE_MS, 1000),
                                  ("WAKE_GAP", preamble.WAKE_GAP_MS, 1000),
                                  ("WAKE_HZ", preamble.WAKE_HZ, 1)):
        found = re.search(rf"\b{name}\s*=\s*([0-9.]+)", html)

        if not found:
            healthy = line(FAIL, f"{name} missing from the page") and healthy
        elif abs(float(found.group(1)) * scale - constant) > 1e-6:
            healthy = line(FAIL, f"{name} differs",
                           f"page {found.group(1)}, this build {constant / scale}") and healthy
        else:
            healthy = line(PASS, f"{name} matches") and healthy

    if not healthy:
        print("\n  The page carries its own copy of the schema, crypto and framing, so its"
              "\n  own self-test only proves it agrees with itself. Regenerate the vectors"
              "\n  in field.html whenever the frame format changes.")

    return healthy


def check_folder_docs():
    """Every folder explains itself, and the explanation still matches what is there.

    A README that names a file which has since been renamed is worse than no README,
    because it is believed. This is the same drift that made field.html quietly wrong.
    """
    import re

    root = _Path(__file__).resolve().parents[1]
    print("\nevery folder explains itself")
    healthy = True

    for folder in ("soundout", "soundout/radio", "soundout/island", "tools",
                   "experiments", "docs"):
        here = root / folder
        readme = here / "README.md"

        if not readme.exists():
            healthy = line(FAIL, f"{folder}/README.md is missing") and healthy
            continue

        text = readme.read_text(encoding="utf-8")
        named = {n for n in re.findall(r"`([A-Za-z_][\w]*\.(?:py|md|svg|html))`", text)}
        missing = sorted(n for n in named if not (here / n).exists()
                         and not (root / n).exists())

        # and the other way round: a file nobody has written a line about
        present = {f.name for f in here.glob("*.py")} | {f.name for f in here.glob("*.svg")}
        present -= {"__init__.py"}
        undocumented = sorted(present - named)

        if missing:
            healthy = line(FAIL, f"{folder}/README.md names files that are gone",
                           ", ".join(missing)) and healthy
        elif undocumented:
            healthy = line(FAIL, f"{folder} has undocumented files",
                           ", ".join(undocumented)) and healthy
        else:
            healthy = line(PASS, f"{folder}", f"{len(named)} file(s) described") and healthy

    return healthy


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
    results = [check_imports(), check_pipeline(), check_relay(),
               check_authority(), check_noise(),
               check_field_page(), check_folder_docs(), check_stale_audio()]

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
