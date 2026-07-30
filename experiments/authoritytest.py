import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island import authority, relay
from soundout.island.reports import build_report, ingest, sign_broadcast
from soundout.island.store import Store
from soundout.island.trust import Authority
from soundout.radio.link import receive, transmit
from soundout.radio.tones import RATE

ISSUED = 500_000


def pad(signal):
    return np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])


def over_air(payload, store=None, bulletin=None):
    return ingest(pad(transmit(payload)), store, bulletin=bulletin)


def orders_arrive():
    print("an order from the base, over real audio\n")

    office = Authority.demo()
    listener = authority.Bulletin(office.public_bytes(), now_minutes=ISSUED)

    body = authority.encode_order(ISSUED, 1, "evacuate now", scope="zone", target=3,
                                  within_hours=2)
    outcome = over_air(sign_broadcast(body, office), bulletin=listener)

    print(f"  heard          : {outcome.get('description', outcome.get('reason'))}")
    print(f"  it is an order : {outcome.get('message', {}).get('kind') == authority.ORDER}")


def forgery_and_replay():
    print("\nwhat a shelter refuses to obey\n")

    office = Authority.demo()
    impostor = Authority()
    body = authority.encode_order(ISSUED, 5, "evacuate now")
    genuine = sign_broadcast(body, office)

    def try_it(label, payload, listener, now=ISSUED):
        message, error = (None, "not a broadcast")
        if len(payload) > 64:
            message, error = listener.accept(payload[:-64], payload[-64:], now_minutes=now)
        verdict = "ACCEPTED" if message else f"refused: {error}"
        print(f"  {label:34s} {verdict}")
        return message

    fresh = lambda: authority.Bulletin(office.public_bytes(), now_minutes=ISSUED)

    try_it("a genuine order", genuine, fresh())
    try_it("signed by somebody else", sign_broadcast(body, impostor), fresh())

    tampered = bytearray(genuine)
    tampered[6] ^= 0x01                      # change the order after it was signed
    try_it("altered after signing", bytes(tampered), fresh())

    listener = fresh()
    try_it("the same order, first time", genuine, listener)
    try_it("the same order, played again", genuine, listener)

    old = sign_broadcast(authority.encode_order(ISSUED - 400, 4, "evacuate now"), office)
    try_it("a recording from 400 min ago", old, fresh())


def digest_saves_airtime():
    """The base saying what it has is worth more than the airtime it costs."""
    print("\nwhat the digest is worth\n")

    office = Authority.demo()
    station = Store()
    listener = authority.Bulletin(office.public_bytes(), now_minutes=ISSUED)

    shelters = [12, 24, 37, 41, 55]
    for shelter in shelters:
        report = build_report(reporter=1000 + shelter, shelter=shelter, people=40,
                              capacity=100, needs=["water"], casualties=0,
                              access="open", minutes=ISSUED - 20)
        over_air(report, station)

    waiting = len(relay.pending(station, limit=99))
    print(f"  a relay is holding             : {waiting} reports to pass on")

    # the base has heard three of the five directly
    holdings = [(shelter, ISSUED - 10) for shelter in shelters[:3]]
    digest = sign_broadcast(authority.encode_digest(ISSUED, 9, holdings), office)

    outcome = over_air(digest, station, bulletin=listener)
    left = len(relay.pending(station, limit=99))

    print(f"  the base says it already has   : {len(holdings)}")
    print(f"  dropped from the queue         : {outcome['suppressed']}")
    print(f"  still to pass on               : {left}")
    station.close()

    # A digest is sent once and heard by every relay within earshot at the same moment,
    # so what it saves scales with how many stations are listening. With a single relay
    # and a handful of shelters it does not pay for itself in airtime at all.
    from soundout.radio.link import duration_seconds
    repeat = duration_seconds(16, RATE, "fast")

    print("\n  net airtime, once the repeats it cancels are counted\n")
    print("  shelters   digest costs      1 relay    2 relays    4 relays")

    for count in (3, 6, 12, 24):
        body = authority.encode_digest(ISSUED, 1, [(s, ISSUED - 5) for s in range(count)])
        cost = len(transmit(sign_broadcast(body, office))) / RATE

        row = f"  {count:8d}   {cost:9.2f} s  "
        for relays in (1, 2, 4):
            row += f"{count * repeat * relays - cost:+10.1f} s"
        print(row)

    print("\n  One relay and three shelters loses half a second. Everything beyond that")
    print("  wins, and the win grows with both the number of shelters acknowledged and")
    print("  the number of stations listening, because the digest is sent once and heard")
    print("  by all of them at the same moment.")
    print("\n  Airtime is not the only return. The digest answers a question a shelter")
    print("  cannot otherwise answer at all: did anybody actually get my report?")


def airtime():
    print("\n\nwhat the two kinds of message cost\n")
    print("  message                        bytes   airtime")

    office = Authority.demo()
    report = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                          needs=["water"], casualties=0, access="open", minutes=ISSUED)
    order = sign_broadcast(authority.encode_order(ISSUED, 1, "evacuate now"), office)
    digest = sign_broadcast(authority.encode_digest(
        ISSUED, 2, [(s, ISSUED - 5) for s in range(12)]), office)

    for label, payload in (("a situation report", report),
                           ("an order", order),
                           ("a digest of 12 shelters", digest)):
        print(f"  {label:30s} {len(payload):5d}   {len(transmit(payload)) / RATE:5.2f} s")

    print("\n  The signature is 64 bytes against a 4-byte tag, and that is the whole cost")
    print("  of the difference: a report only has to prove it came from one shelter to")
    print("  one base, while an order has to prove itself to everybody without handing")
    print("  anybody the means to write one.")


if __name__ == "__main__":
    orders_arrive()
    forgery_and_replay()
    digest_saves_airtime()
    airtime()
