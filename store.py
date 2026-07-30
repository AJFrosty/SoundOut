import sqlite3
from datetime import datetime, timezone

from situation import ACCESS, NEEDS, decode_report, needs_list

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    raw           TEXT PRIMARY KEY,
    shelter       INTEGER NOT NULL,
    reporter      INTEGER NOT NULL,
    minutes       INTEGER NOT NULL,
    occupancy     INTEGER NOT NULL,
    capacity      INTEGER NOT NULL,
    needs         INTEGER NOT NULL,
    casualties    INTEGER NOT NULL,
    access        INTEGER NOT NULL,
    authenticated INTEGER NOT NULL,
    heard_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS by_shelter ON observations(shelter, minutes DESC, reporter DESC);
"""

CURRENT_VIEW = """
SELECT shelter, reporter, minutes, occupancy, capacity, needs, casualties,
       access, authenticated, heard_at
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY shelter ORDER BY minutes DESC, reporter DESC
    ) AS rank
    FROM observations
    WHERE authenticated = 1 OR :include_unverified = 1
)
WHERE rank = 1
ORDER BY shelter
"""


class Store:
    def __init__(self, path=":memory:"):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def add(self, report_bytes, authenticated, heard_at=None):
        fields = decode_report(report_bytes)
        stamp = heard_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO observations VALUES "
            "(:raw, :shelter, :reporter, :minutes, :occupancy, :capacity, :needs, "
            ":casualties, :access, :authenticated, :heard_at)",
            {
                "raw": report_bytes.hex(),
                "shelter": fields["shelter"],
                "reporter": fields["reporter"],
                "minutes": fields["minutes"],
                "occupancy": fields["occupancy"],
                "capacity": fields["capacity"],
                "needs": fields["needs"],
                "casualties": fields["casualties"],
                "access": fields["access"],
                "authenticated": 1 if authenticated else 0,
                "heard_at": stamp,
            },
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def observation_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

    def view(self, include_unverified=False):
        rows = self.connection.execute(
            CURRENT_VIEW, {"include_unverified": 1 if include_unverified else 0}
        ).fetchall()

        return [
            {
                "shelter": row["shelter"],
                "reporter": row["reporter"],
                "minutes": row["minutes"],
                "occupancy": row["occupancy"],
                "capacity": row["capacity"],
                "needs": needs_list(row["needs"]),
                "casualties": row["casualties"],
                "access": ACCESS[row["access"]],
                "authenticated": bool(row["authenticated"]),
                "heard_at": row["heard_at"],
                "full": row["occupancy"] >= row["capacity"],
            }
            for row in rows
        ]

    def fingerprint(self, include_unverified=False):
        return tuple(
            (r["shelter"], r["reporter"], r["minutes"], r["occupancy"], r["capacity"],
             tuple(r["needs"]), r["casualties"], r["access"])
            for r in self.view(include_unverified)
        )

    def summary(self, include_unverified=False):
        shelters = self.view(include_unverified)

        demand = {}
        for shelter in shelters:
            for need in shelter["needs"]:
                demand[need] = demand.get(need, 0) + shelter["occupancy"]

        ranked = sorted(demand.items(), key=lambda item: (-item[1], NEEDS.index(item[0])))

        return {
            "shelters": len(shelters),
            "people": sum(s["occupancy"] for s in shelters),
            "casualties": sum(s["casualties"] for s in shelters),
            "full_shelters": [s["shelter"] for s in shelters if s["full"]],
            "cut_off": [s["shelter"] for s in shelters
                        if s["access"] in ("impassable", "flooded", "bridge down", "landslide")],
            "needs_by_people_affected": ranked,
            "observations": self.observation_count(),
        }

    def close(self):
        self.connection.close()
