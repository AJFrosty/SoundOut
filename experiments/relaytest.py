import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

from soundout.island import relay
from soundout.island.reports import build_report, ingest
from soundout.island.store import Store
from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import duration_seconds, transmit
from soundout.radio.tones import RATE

RNG = np.random.default_rng(7)

SLOT_S = duration_seconds(16, RATE, "fast") + 0.4     # one frame, plus a breath


def hop_keeps_authentication():
    """A relayed report must still prove who wrote it, not who repeated it."""
    print("an observation crossing a station, over real audio\n")

    original = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                            needs=["insulin"], casualties=2, access="impassable",
                            minutes=1_234_567)

    middle, base = Store(), Store()

    heard = ingest(pad(transmit(original)), middle)
    print(f"  station hears it     : {'authentic' if heard['authentic'] else 'FAILED'}")

    waiting = relay.pending(middle)
    print(f"  waiting to pass on   : {len(waiting)}")

    repeated = relay.payload_of(waiting[0])
    print(f"  repeats byte for byte: {repeated == original}")

    arrived = ingest(pad(transmit(repeated)), base)
    print(f"  base hears it        : {'authentic' if arrived['authentic'] else 'FAILED'}")
    print(f"  base sees the same   : {base.fingerprint() == middle.fingerprint()}")

    relay.mark_relayed(middle, waiting[0])
    print(f"  station repeats again: {len(relay.pending(middle))} waiting  "
          f"(once each is what makes it stop)")

    middle.close()
    base.close()


def pad(signal):
    return np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])


class Island:
    """Stations on a map, talking in slots, colliding when they talk over each other.

    Running the real modem for every hop would take hours of wall clock, so hops are
    simulated at the packet level. The per-link delivery odds come from the measured
    curve: solid well inside range, falling off at the edge, nothing beyond it.
    """

    def __init__(self, count, span, reach, rng, spread_slots=4, own_repeats=3):
        self.rng = rng
        self.reach = reach
        self.spread = spread_slots
        self.own_repeats = own_repeats

        # the base sits at the origin; shelters are scattered around it
        angles = rng.uniform(0, 2 * np.pi, count)
        radii = span * np.sqrt(rng.uniform(0, 1, count))
        self.places = [(0.0, 0.0)] + list(zip(radii * np.cos(angles),
                                              radii * np.sin(angles)))

        self.held = [set() for _ in self.places]
        self.repeated = [set() for _ in self.places]
        self.said_own = [0] * len(self.places)
        self.waiting_until = [None] * len(self.places)
        self.busy = [False] * len(self.places)

        for shelter in range(1, len(self.places)):
            self.held[shelter].add(shelter)

    def hears(self, sender, listener):
        a, b = self.places[sender], self.places[listener]
        distance = np.hypot(a[0] - b[0], a[1] - b[1])

        if distance >= self.reach:
            return False
        if distance <= self.reach * 0.8:
            return True

        edge = (self.reach - distance) / (self.reach * 0.2)
        return self.rng.uniform() < edge

    def connected(self):
        """The most any protocol could deliver: who is joined to the base by some chain.

        A shelter with no neighbour within reach is not a protocol failure, it is a
        geography failure, and it belongs in the ceiling rather than in the score.

        Any link with a chance of delivering counts, not only the reliable ones: given
        enough attempts a marginal link does eventually get a frame through.
        """
        seen, edge = {0}, [0]

        while edge:
            here = edge.pop()
            for other in range(len(self.places)):
                a, b = self.places[here], self.places[other]
                if other not in seen and np.hypot(a[0] - b[0], a[1] - b[1]) < self.reach:
                    seen.add(other)
                    edge.append(other)

        return (len(seen) - 1) / (len(self.places) - 1)

    def pending(self, station, relaying):
        """What this station would say next, its own situation first.

        A shelter keeps repeating its own status whether or not it relays; that is what
        anyone with a radio would do, and it is what makes the comparison fair.
        """
        if self.said_own[station] < self.own_repeats:
            return station

        if relaying:
            others = sorted(self.held[station] - self.repeated[station] - {station})
            if others:
                return others[0]

        return None

    def run(self, slots, relaying=True):
        transmissions = 0

        for slot in range(slots):
            speaking = {}

            for station in range(1, len(self.places)):     # the base only listens
                waiting = self.pending(station, relaying)

                if waiting is None:
                    self.waiting_until[station] = None
                    continue

                # carrier sense: do not talk over a transmission already in progress.
                # Deferring re-rolls the wait, or every deferred station would resume in
                # the same instant and collide all over again.
                if self.busy[station]:
                    self.waiting_until[station] = None
                    continue

                if self.waiting_until[station] is None:
                    self.waiting_until[station] = slot + int(self.rng.integers(0, self.spread + 1))
                    continue

                if slot >= self.waiting_until[station]:
                    speaking[station] = waiting

            transmissions += len(speaking)

            for listener in range(len(self.places)):
                reaching = [s for s in speaking if s != listener and self.hears(s, listener)]

                self.busy[listener] = bool(reaching)
                # two voices at once and the listener gets neither
                if len(reaching) == 1:
                    self.held[listener].add(speaking[reaching[0]])

            for station, sent in speaking.items():
                self.busy[station] = False
                self.waiting_until[station] = None

                if sent == station:
                    self.said_own[station] += 1
                else:
                    self.repeated[station].add(sent)

        return {
            "delivered": len(self.held[0]) / (len(self.places) - 1),
            "transmissions": transmissions,
        }


def island_sweep(runs=25):
    print("\n\nreports reaching the base across an island\n")
    print("  reach   out of direct range   no relay   relaying   transmissions")

    for reach in (34, 26, 20, 16):
        stranded = plain = relayed = airtime = 0

        for _ in range(runs):
            seed = RNG.integers(1 << 30)

            island = Island(12, 30, reach, np.random.default_rng(seed))
            stranded += sum(1 for s in range(1, 13) if not island.hears(s, 0)) / 12
            plain += island.run(60, relaying=False)["delivered"]

            island = Island(12, 30, reach, np.random.default_rng(seed))
            outcome = island.run(60, relaying=True)
            relayed += outcome["delivered"]
            airtime += outcome["transmissions"]

        print(f"  {reach:5d}   {stranded / runs:19.0%}   {plain / runs:8.0%}   "
              f"{relayed / runs:8.0%}   {airtime / runs:13.0f}")


def settling(runs=25, reach=20):
    """The shape that matters: one plateaus, the other keeps climbing."""
    print(f"\n\nhow complete the picture is over time (reach {reach})\n")
    print("  minutes   no relay   relaying   ceiling")

    for slots in (20, 40, 80, 160, 320, 640):
        plain = relayed = ceiling = 0

        for _ in range(runs):
            seed = RNG.integers(1 << 30)
            for relaying in (False, True):
                island = Island(12, 30, reach, np.random.default_rng(seed),
                                own_repeats=max(3, slots // 10))
                got = island.run(slots, relaying=relaying)["delivered"]
                if relaying:
                    relayed += got
                    ceiling += island.connected()
                else:
                    plain += got

        print(f"  {slots * SLOT_S / 60:7.1f}   {plain / runs:8.0%}   "
              f"{relayed / runs:8.0%}   {ceiling / runs:7.0%}")

    print("\n  The ceiling is how many shelters are joined to the base by some chain of")
    print("  hops at all. The rest are alone on the map and no protocol reaches them.")
    print("  Without relaying the curve stops at whoever can reach the base directly,")
    print("  and waiting longer does not move it. With relaying it climbs to the ceiling.")


def spread_sweep(runs=25):
    print("\n\nwhen everyone answers at once\n")
    print("  wait spread   delivered   transmissions   minutes to settle")

    for spread in (0, 1, 2, 4, 8, 16):
        delivered = airtime = 0

        for _ in range(runs):
            island = Island(12, 30, 20, np.random.default_rng(RNG.integers(1 << 30)),
                            spread_slots=spread)
            outcome = island.run(60)
            delivered += outcome["delivered"]
            airtime += outcome["transmissions"]

        print(f"  {spread:11d}   {delivered / runs:8.0%}   {airtime / runs:13.0f}   "
              f"{60 * SLOT_S / 60:17.1f}")


if __name__ == "__main__":
    hop_keeps_authentication()
    island_sweep()
    settling()
    spread_sweep()
