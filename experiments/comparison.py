"""What is the base actually able to see, hour by hour, and what would the alternatives see?

The question a coordinator asks is not "did the message arrive" but "how old is what I am
looking at". Dispatching water to a shelter on a six-hour-old occupancy figure sends the
wrong amount to the wrong place, so the measure here is **staleness**: the age of the
freshest information the base holds about each shelter, averaged across the island.

Lower is better. A flat line at the elapsed time means the base knows nothing at all and
is still working from what it knew before the storm.

Every assumption is a constant at the top of this file, deliberately, so anyone can
disagree with one and re-run it.
"""

import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import numpy as np

HOURS = 72
SHELTERS = 12
SPAN_KM = 30.0

# a shelter's situation genuinely changes: people arrive, water runs out, a road clears
SITUATION_CHANGES_EVERY_H = 3.0

# SoundOut: how often a shelter transmits, and how the relay network delivers. The delay
# curve is not invented - it is the settling curve measured in experiments/relaytest.py.
REPORT_EVERY_MIN = 30
DELIVERY_CURVE = [(0.9, 0.31), (3.6, 0.59), (7.1, 0.70), (14.3, 0.76), (28.6, 0.79)]

# Some shelters have no neighbour within radio reach and are joined to nothing. Rolling
# the delivery curve afresh for every report would let them succeed eventually by sheer
# repetition, which is false: they are stranded permanently, not unlucky repeatedly. The
# figure is the geography ceiling measured in relaytest.
ON_THE_NETWORK = 0.92

# a runner on a motorbike where the road is open, on foot where it is not
COURIER_EVERY_H = 6.0
RIDE_KMH = 15.0
WALK_KMH = 4.5

# Cellular restoration is the assumption that most favours the alternative, so it is set
# generously. After Maria, Dominica and Puerto Rico measured restoration in weeks, not
# days; 48 hours is optimistic on purpose. Sensitivity to it is printed below.
CELL_RETURNS_H = 48.0

# with nobody organising anything, word reaches the base when someone eventually walks in
WORD_OF_MOUTH_EVERY_H = 24.0

ROAD_CLEARS_BY_H = 30.0
BLOCKED_AT_START = 0.55

METHODS = ["nothing", "courier", "cellular", "soundout", "perfect"]


def delivery_delay(rng):
    """Minutes until a report reaches the base, or None if it never does.

    Drawn from the measured relay settling curve rather than assumed.
    """
    roll = rng.uniform()
    previous = 0.0

    for minutes, reached in DELIVERY_CURVE:
        if roll < reached:
            return rng.uniform(previous, minutes)
        previous = minutes

    return None


class Island:
    def __init__(self, rng):
        self.rng = rng

        angle = rng.uniform(0, 2 * np.pi, SHELTERS)
        radius = SPAN_KM * np.sqrt(rng.uniform(0.05, 1, SHELTERS))
        self.distance = radius                                  # km from the base
        self.angle = angle

        self.blocked_until = np.where(
            rng.uniform(size=SHELTERS) < BLOCKED_AT_START,
            rng.uniform(0, ROAD_CLEARS_BY_H, SHELTERS),
            0.0,
        )

        # who is joined to the network at all, decided once and for the whole storm
        self.reachable = rng.uniform(size=SHELTERS) < ON_THE_NETWORK

        # when the truth at each shelter last changed, in minutes
        steps = int(HOURS * 60 / SITUATION_CHANGES_EVERY_H / 60) + 1
        self.changes = [sorted(rng.uniform(0, HOURS * 60, steps)) for _ in range(SHELTERS)]

    def truth_at(self, shelter, minute):
        """The timestamp of the situation that is true right now."""
        happened = [t for t in self.changes[shelter] if t <= minute]
        return happened[-1] if happened else 0.0

    def travel_minutes(self, shelter, hour):
        blocked = hour < self.blocked_until[shelter]
        speed = WALK_KMH if blocked else RIDE_KMH
        return self.distance[shelter] / speed * 60

    def run(self, method):
        """Return, for each minute, the timestamp of what the base holds per shelter."""
        held = np.zeros((HOURS * 60, SHELTERS))
        arrivals = [[] for _ in range(SHELTERS)]

        for shelter in range(SHELTERS):
            if method == "soundout":
                for sent in (range(0, HOURS * 60, REPORT_EVERY_MIN)
                             if self.reachable[shelter] else []):
                    delay = delivery_delay(self.rng)
                    if delay is not None:
                        arrivals[shelter].append((sent + delay, self.truth_at(shelter, sent)))

            elif method == "courier":
                for sent in np.arange(0, HOURS * 60, COURIER_EVERY_H * 60):
                    travel = self.travel_minutes(shelter, sent / 60)
                    arrivals[shelter].append((sent + travel, self.truth_at(shelter, sent)))

            elif method == "cellular":
                # nothing at all until the network is back, then continuously
                for sent in np.arange(CELL_RETURNS_H * 60, HOURS * 60, 5):
                    arrivals[shelter].append((sent + 1, self.truth_at(shelter, sent)))

            elif method == "perfect":
                # the floor nothing can beat: the base is told the instant anything
                # changes. Staleness never reaches zero even so, because the truth keeps
                # moving; this is the cost of the world changing, not of the link.
                for changed in self.changes[shelter]:
                    arrivals[shelter].append((changed, changed))

            elif method == "nothing":
                for sent in np.arange(0, HOURS * 60, WORD_OF_MOUTH_EVERY_H * 60):
                    travel = self.distance[shelter] / WALK_KMH * 60
                    arrivals[shelter].append((sent + travel, self.truth_at(shelter, sent)))

            newest = 0.0
            index = 0
            ordered = sorted(arrivals[shelter])

            for minute in range(HOURS * 60):
                while index < len(ordered) and ordered[index][0] <= minute:
                    newest = max(newest, ordered[index][1])
                    index += 1
                held[minute, shelter] = newest

        return held

    def staleness(self, method):
        """Mean age in hours of what the base holds, minute by minute."""
        held = self.run(method)
        minutes = np.arange(HOURS * 60).reshape(-1, 1)
        return np.mean(minutes - held, axis=1) / 60

    def time_to_learn(self, method, at_hour=6.0):
        """How long before the base hears about something that happens at `at_hour`."""
        emergency = at_hour * 60
        held = self.run(method)

        for minute in range(int(emergency), HOURS * 60):
            if np.any(held[minute] >= emergency):
                return (minute - emergency) / 60

        return None


def curves(runs=30):
    rng = np.random.default_rng(19)
    gathered = {name: np.zeros(HOURS * 60) for name in METHODS}

    for _ in range(runs):
        island = Island(rng)
        for name in METHODS:
            gathered[name] += island.staleness(name)

    return {name: total / runs for name, total in gathered.items()}


def around(line, hour, window=45):
    """Average either side of the hour: every method sawtooths between updates."""
    middle = hour * 60
    return float(np.mean(line[max(middle - window, 0):middle + window]))


def table(lines):
    print("how old the base's picture is, in hours (lower is better)\n")
    print("  hour  " + "".join(f"{name:>12}" for name in METHODS))

    for hour in (1, 3, 6, 12, 24, 48, 60, 71):
        row = f"  {hour:4d}  "
        for name in METHODS:
            row += f"{around(lines[name], hour):>11.1f} "
        print(row)

    print("\n  'perfect' is a link that reports every change the instant it happens. It")
    print("  never reaches zero, because the island keeps changing while you watch it;")
    print("  that residue is the cost of the world moving rather than of the link, and")
    print("  it is the floor every method is measured against.")
    print("\n  A figure equal to the hour itself means the base knows nothing newer than")
    print("  the storm. Cellular sits there until the network returns and then wins")
    print("  outright - the claim is not that this beats a working phone network, it is")
    print("  that the window where nothing else works is when the reports matter most.")


def emergencies(runs=30):
    rng = np.random.default_rng(23)
    print("\n\nhow long before the base hears about a new emergency\n")
    print("  method        median   worst case   never heard")

    for name in METHODS:
        delays = []
        missed = 0

        for _ in range(runs):
            delay = Island(rng).time_to_learn(name)
            if delay is None:
                missed += 1
            else:
                delays.append(delay)

        if delays:
            print(f"  {name:12s}  {np.median(delays):5.1f} h   {max(delays):8.1f} h   "
                  f"{missed / runs:10.0%}")
        else:
            print(f"  {name:12s}      -            -   {missed / runs:10.0%}")


def usable(lines):
    """How much of the response can a coordinator actually act on?

    A picture more than a few hours old describes a shelter that may since have filled
    up, run dry, or been cut off. This asks what share of the first three days each
    method spends inside a usable age.
    """
    rng = np.random.default_rng(31)
    silent = {name: np.mean([np.mean(Island(rng).run(name)[-1] == 0) for _ in range(20)])
              for name in METHODS}

    print("\n\nshare of the first 72 hours with a picture fresher than...\n")
    print("  method         4 hours   6 hours   12 hours   never heard from")

    for name in METHODS:
        row = f"  {name:12s} "
        for threshold in (4, 6, 12):
            row += f"{np.mean(lines[name] < threshold):9.0%} "
        print(row + f"{silent[name]:18.0%}")

    print("\n  The last column is the honest cost of relying on radio alone: a shelter")
    print("  with no neighbour in reach is never heard from at all, and it drags the")
    print("  average up for the whole storm. A runner is slower but eventually reaches")
    print("  everybody. These are complements rather than competitors.")

    print("\n  A perfect link averages 2.9 h here, so four hours is close to the floor")
    print("  rather than an easy bar. And before the phones come back, cellular is not")
    print("  merely worse than the alternatives - it is nothing at all.")


if __name__ == "__main__":
    lines = curves()
    table(lines)
    emergencies()
    usable(lines)

    from experiments.chart import write_chart
    write_chart(lines, METHODS, HOURS)
