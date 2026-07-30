import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island.reports import build_report, ingest
from soundout.island.situation import decode_report, encode_report
from soundout.island.store import Store
from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import transmit
from soundout.radio.tones import RATE

RNG = np.random.default_rng(41)

SHELTERS = [
    dict(reporter=1041, shelter=37, people=42, capacity=60,
         needs=["water", "insulin"], casualties=2, access="impassable", minutes=1_000_100),
    dict(reporter=1002, shelter=12, people=180, capacity=180,
         needs=["water", "food"], casualties=0, access="open", minutes=1_000_105),
    dict(reporter=1003, shelter=5, people=25, capacity=90,
         needs=["insulin", "medic"], casualties=1, access="debris", minutes=1_000_090),
    dict(reporter=1041, shelter=37, people=51, capacity=60,
         needs=["water", "insulin", "fuel"], casualties=3, access="impassable",
         minutes=1_000_160),
]


def report_line(outcome):
    if not outcome["stored"]:
        print(f"  lost: {outcome['reason']}")
        return

    mark = "OK " if outcome["authentic"] else "!! "
    print(f"  {mark}{outcome['description']}")
    if not outcome["authentic"]:
        print("      authentication FAILED - stored but not trusted")


def over_air(payload, snr_db):
    signal = transmit(payload, amplitude=0.6)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
    return through_simulated_channel(padded, snr_db, RNG)


def run(snr_db=5.0):
    store = Store()
    print(f"four transmissions through a {snr_db:.0f} dB channel, in a shuffled order\n")

    payloads = [build_report(**s) for s in SHELTERS]
    order = list(RNG.permutation(len(payloads)))

    for index in order:
        heard = over_air(payloads[index], snr_db)
        report_line(ingest(heard, store))

    print("\nthe picture that assembled itself:")
    for shelter in store.view():
        needs = ", ".join(shelter["needs"]) or "nothing urgent"
        print(f"  shelter {shelter['shelter']:3d}  {shelter['occupancy']:3d}/"
              f"{shelter['capacity']:<3d}  {shelter['access']:11s}  {needs}")

    summary = store.summary()
    print(f"\n  {summary['people']} people across {summary['shelters']} shelters, "
          f"{summary['casualties']} casualties")
    print(f"  cut off: {summary['cut_off']}   full: {summary['full_shelters']}")
    print("  needs by people affected:", ", ".join(
        f"{need} ({people})" for need, people in summary["needs_by_people_affected"]))

    latest = [s for s in store.view() if s["shelter"] == 37][0]
    print(f"\n  shelter 37 shows {latest['occupancy']} people — the later of its two "
          f"reports won, whichever order they arrived in")

    store.close()


def forgery_is_rejected():
    print("\na looter with a stolen handset invents a report")
    store = Store()

    genuine = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                    needs=["water"], casualties=0, access="open", minutes=1_000_200)
    report_line(ingest(over_air(genuine, 20), store))

    fake_body = encode_report(reporter=1041, shelter=37, occupancy=0, capacity=60,
                              needs=[], casualties=0, access="open", minutes=1_000_300)
    forged = fake_body + b"\x00\x00\x00\x00"
    report_line(ingest(over_air(forged, 20), store))

    trusted = store.view()
    everything = store.view(include_unverified=True)

    print(f"  the forged report is newer, so it would win on timestamp alone")
    print(f"  trusted picture   : {trusted[0]['occupancy']} people (the genuine report)")
    print(f"  if unverified data were included: {everything[0]['occupancy']} people "
          f"(the forgery)")
    print(f"  both are kept — {store.observation_count()} observations on record — but "
          f"only the authenticated one counts")
    store.close()


if __name__ == "__main__":
    run()
    forgery_is_rejected()
