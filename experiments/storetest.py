import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import itertools
import random

from soundout.island.situation import encode_report
from soundout.island.store import Store

RANDOM = random.Random(5)


def report(shelter, reporter, minutes, occupancy=40, capacity=60, needs=("water",),
           casualties=0, access="open"):
    return encode_report(
        reporter=reporter, shelter=shelter, occupancy=occupancy, capacity=capacity,
        needs=list(needs), casualties=casualties, access=access, minutes=minutes)


def sample_reports(count=24):
    reports = []
    for i in range(count):
        reports.append(report(
            shelter=RANDOM.randint(1, 6),
            reporter=RANDOM.randint(1000, 1005),
            minutes=RANDOM.randint(1_000_000, 1_000_500),
            occupancy=RANDOM.randint(0, 200),
            capacity=200,
            needs=RANDOM.sample(["water", "food", "insulin", "fuel", "medic"],
                                RANDOM.randint(0, 3)),
            casualties=RANDOM.randint(0, 5),
            access=RANDOM.choice(["open", "debris", "impassable", "flooded"]),
        ))
    return reports


def order_independence(shuffles=200):
    reports = sample_reports()

    reference = Store()
    for r in reports:
        reference.add(r, authenticated=True)
    expected = reference.fingerprint()

    mismatches = 0
    for _ in range(shuffles):
        shuffled = reports[:]
        RANDOM.shuffle(shuffled)

        store = Store()
        for r in shuffled:
            store.add(r, authenticated=True)

        if store.fingerprint() != expected:
            mismatches += 1
        store.close()

    print(f"order independence : {shuffles - mismatches}/{shuffles} orderings agree "
          f"({'PASS' if mismatches == 0 else 'FAIL'})")
    reference.close()


def idempotence():
    once = Store()
    twice = Store()

    for r in sample_reports(12):
        once.add(r, authenticated=True)
        twice.add(r, authenticated=True)
        twice.add(r, authenticated=True)
        twice.add(r, authenticated=True)

    same = once.fingerprint() == twice.fingerprint()
    print(f"idempotence        : hearing a report 3 times equals hearing it once "
          f"({'PASS' if same else 'FAIL'})")
    print(f"                     {twice.observation_count()} rows stored, duplicates ignored")
    once.close()
    twice.close()


def newest_wins():
    store = Store()
    store.add(report(shelter=3, reporter=1001, minutes=1000, occupancy=10), True)
    store.add(report(shelter=3, reporter=1002, minutes=2000, occupancy=90), True)
    store.add(report(shelter=3, reporter=1003, minutes=1500, occupancy=50), True)

    shelter = store.view()[0]
    print(f"newest wins        : occupancy {shelter['occupancy']} from reporter "
          f"{shelter['reporter']} ({'PASS' if shelter['occupancy'] == 90 else 'FAIL'})")
    store.close()


def tie_break():
    fingerprints = set()

    for order in itertools.permutations([1001, 1002, 1003]):
        store = Store()
        for reporter in order:
            store.add(report(shelter=4, reporter=reporter, minutes=5000,
                             occupancy=reporter - 1000), True)
        fingerprints.add(store.fingerprint())
        store.close()

    print(f"tie break          : identical timestamps resolve the same way in all "
          f"{len(list(itertools.permutations([1001, 1002, 1003])))} orders "
          f"({'PASS' if len(fingerprints) == 1 else 'FAIL'})")


def unverified_excluded():
    store = Store()
    store.add(report(shelter=7, reporter=1001, minutes=1000, occupancy=10), True)
    store.add(report(shelter=7, reporter=1099, minutes=9000, occupancy=999,
                     capacity=1000), False)

    trusted = store.view()[0]["occupancy"]
    everything = store.view(include_unverified=True)[0]["occupancy"]

    print(f"forged report      : ignored by default (occupancy {trusted}), "
          f"visible only on request ({everything}) "
          f"({'PASS' if trusted == 10 and everything == 999 else 'FAIL'})")
    store.close()


def picture():
    store = Store()
    store.add(report(shelter=37, reporter=1041, minutes=1_234_567, occupancy=42,
                     capacity=60, needs=["water", "insulin"], casualties=2,
                     access="impassable"), True)
    store.add(report(shelter=12, reporter=1002, minutes=1_234_570, occupancy=180,
                     capacity=180, needs=["water", "food"], casualties=0,
                     access="open"), True)
    store.add(report(shelter=5, reporter=1003, minutes=1_234_540, occupancy=25,
                     capacity=90, needs=["insulin"], casualties=1, access="debris"), True)

    summary = store.summary()
    print("\nthe island picture from three shelters")
    print(f"  shelters reporting : {summary['shelters']}")
    print(f"  people sheltered   : {summary['people']}")
    print(f"  casualties         : {summary['casualties']}")
    print(f"  full shelters      : {summary['full_shelters']}")
    print(f"  cut off            : {summary['cut_off']}")
    print("  needs, ranked by people affected:")
    for need, people in summary["needs_by_people_affected"]:
        print(f"    {need:10s} {people:4d} people")
    store.close()


if __name__ == "__main__":
    order_independence()
    idempotence()
    newest_wins()
    tie_break()
    unverified_excluded()
    picture()
