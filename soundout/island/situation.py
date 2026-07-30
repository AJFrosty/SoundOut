VERSION = 1
REPORT_BYTES = 12

NEEDS = [
    "water", "food", "insulin", "dialysis", "baby formula", "fuel",
    "tarpaulin", "medic", "evacuation", "sanitation", "comms", "power",
]

ACCESS = [
    "open", "debris", "impassable", "flooded", "bridge down", "landslide",
    "unknown", "reserved",
]

FIELDS = [
    ("version", 3),
    ("reporter", 13),
    ("shelter", 12),
    ("occupancy", 10),
    ("capacity", 10),
    ("needs", 12),
    ("casualties", 7),
    ("access", 3),
    ("minutes", 22),
    ("reserved", 4),
]


class BitWriter:
    def __init__(self):
        self.value = 0
        self.length = 0

    def write(self, number, bits):
        limit = (1 << bits) - 1
        if not 0 <= number <= limit:
            raise ValueError(f"{number} does not fit in {bits} bits (max {limit})")

        self.value = (self.value << bits) | number
        self.length += bits
        return self

    def to_bytes(self):
        if self.length % 8:
            raise ValueError(f"{self.length} bits is not a whole number of bytes")
        return self.value.to_bytes(self.length // 8, "big")


class BitReader:
    def __init__(self, data):
        self.value = int.from_bytes(data, "big")
        self.remaining = len(data) * 8

    def read(self, bits):
        self.remaining -= bits
        if self.remaining < 0:
            raise ValueError("ran out of bits")
        return (self.value >> self.remaining) & ((1 << bits) - 1)


def needs_mask(names):
    mask = 0
    for name in names:
        if name not in NEEDS:
            raise ValueError(f"unknown need {name!r}; choose from: {', '.join(NEEDS)}")
        mask |= 1 << NEEDS.index(name)
    return mask


def access_index(access):
    if isinstance(access, str):
        if access not in ACCESS:
            raise ValueError(f"unknown access state {access!r}; "
                             f"choose from: {', '.join(ACCESS)}")
        return ACCESS.index(access)

    if not isinstance(access, int) or not 0 <= access < len(ACCESS):
        raise ValueError(f"access must be one of: {', '.join(ACCESS)}")

    return access


def needs_list(mask):
    return [name for i, name in enumerate(NEEDS) if mask & (1 << i)]


def encode_report(reporter, shelter, occupancy, capacity, needs, casualties, access, minutes):
    writer = BitWriter()
    values = {
        "version": VERSION,
        "reporter": reporter,
        "shelter": shelter,
        "occupancy": occupancy,
        "capacity": capacity,
        "needs": needs if isinstance(needs, int) else needs_mask(needs),
        "casualties": casualties,
        "access": access_index(access),
        "minutes": minutes,
        "reserved": 0,
    }

    for name, bits in FIELDS:
        try:
            writer.write(values[name], bits)
        except ValueError as error:
            raise ValueError(f"{name}: {error}") from None

    return writer.to_bytes()


def decode_report(data):
    if len(data) != REPORT_BYTES:
        raise ValueError(f"a report is {REPORT_BYTES} bytes, got {len(data)}")

    reader = BitReader(data)
    report = {name: reader.read(bits) for name, bits in FIELDS}

    report["needs_names"] = needs_list(report["needs"])
    report["access_name"] = ACCESS[report["access"]]
    return report


def describe(report):
    if isinstance(report, (bytes, bytearray)):
        report = decode_report(report)

    needs = ", ".join(report["needs_names"]) or "nothing urgent"
    casualties = f", {report['casualties']} casualties" if report["casualties"] else ""

    return (f"Shelter {report['shelter']}: {report['occupancy']} of "
            f"{report['capacity']} places used, needs {needs}{casualties}, "
            f"access {report['access_name']}")


def field_limits():
    return {name: (1 << bits) - 1 for name, bits in FIELDS}
