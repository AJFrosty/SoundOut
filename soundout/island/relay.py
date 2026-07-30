"""Passing on what you heard.

A station that only speaks for itself is a walkie-talkie. A station that repeats what it
heard is a network: a shelter behind a hill reaches the base through a neighbour, and the
two ends never have to be awake at the same moment.

Three rules keep that from becoming a broadcast storm.

**Forward the original bytes, tag and all.** A relay repeats an observation exactly as it
arrived. It never re-signs, so it cannot forge; it can only choose what to repeat. The
base still checks the tag of whoever first wrote the report, however many stations it
crossed on the way.

**Each station repeats each observation once.** That single rule is what makes the traffic
terminate. With N stations, an observation can be transmitted at most N times no matter
how the island is shaped, because every station is a station that has already spoken.
There is no hop counter to carry and nothing to agree on beforehand.

**Airtime is the scarce thing.** A report takes 2.68 s to send. When several are waiting,
the order matters, so they go out worst-first rather than newest-first: a shelter with
casualties and no insulin is worth more airtime than one that is comfortable.
"""

from .situation import ACCESS, NEEDS

LIFE_SAFETY = ("insulin", "dialysis", "medic", "evacuation")
CUT_OFF = ("impassable", "flooded", "bridge down", "landslide")


def urgency(row):
    """How badly this observation needs someone else's airtime.

    Deliberately blunt and readable rather than tuned. Anyone can disagree with the
    weights, and should be able to see exactly what they are disagreeing with.
    """
    needs = {NEEDS[i] for i in range(len(NEEDS)) if row["needs"] >> i & 1}
    score = 0

    score += 40 if row["casualties"] else 0
    score += 25 if needs & set(LIFE_SAFETY) else 0
    score += 15 if ACCESS[row["access"]] in CUT_OFF else 0
    score += 10 if row["occupancy"] >= row["capacity"] else 0
    score += 5 if "water" in needs else 0

    return score


def pending(store, limit=8, include_unverified=False):
    """The observations this station has heard, believes, and has not yet passed on."""
    rows = store.connection.execute(
        "SELECT * FROM observations "
        "WHERE relayed = 0 AND tag != '' AND (authenticated = 1 OR :any = 1)",
        {"any": 1 if include_unverified else 0},
    ).fetchall()

    ordered = sorted(rows, key=lambda row: (-urgency(row), -row["minutes"]))
    return ordered[:limit]


def payload_of(row):
    """The bytes to put back on the air: exactly what the reporter originally sent."""
    return bytes.fromhex(row["raw"]) + bytes.fromhex(row["tag"])


def suppress(store, holdings):
    """Stop repeating what the base has already told us it holds.

    The base periodically broadcasts a digest of the newest report it has from each
    shelter. Anything at or behind that mark is home; repeating it spends airtime to tell
    somebody something they said first. Returns how many were dropped from the queue.
    """
    dropped = 0

    for shelter, minutes in holdings:
        cursor = store.connection.execute(
            "UPDATE observations SET relayed = relayed + 1 "
            "WHERE shelter = ? AND minutes <= ? AND relayed = 0",
            (shelter, minutes),
        )
        dropped += cursor.rowcount

    store.connection.commit()
    return dropped


def mark_relayed(store, row):
    store.connection.execute(
        "UPDATE observations SET relayed = relayed + 1 WHERE raw = ?", (row["raw"],))
    store.connection.commit()


def backoff(rng, spread_s):
    """How long to wait before repeating something.

    Every station that heard a report wants to repeat it, and they all heard it at the
    same instant. Transmitting straight away guarantees they collide, so each waits a
    random slice of a window instead.
    """
    return rng.uniform(0.0, spread_s)
