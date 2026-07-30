"""Messages that travel the other way: from the base out to the shelters.

Until now information only flowed inwards. A shelter transmitted into silence and never
learned whether anyone heard it, and the base had no way to tell anyone anything.

Two kinds of message go outwards, and they are different problems.

**An order** - evacuate, boil water before drinking, a collection point is open. This is
the message somebody would want to forge. A shelter must be able to verify it came from
the emergency office without holding any secret that would let it *write* one, which rules
out the 4-byte HMAC used for reports: a shared secret good enough to check a message is
also good enough to forge one. That is what the 64-byte Ed25519 signature buys, and it is
sixteen times the size of a tag for exactly that reason.

**A digest** - a list of what the base already holds. It answers the question a shelter
cannot otherwise answer, which is whether its report ever arrived, and it lets a relay
stop repeating things that are already home. Airtime saved is airtime available.

Both carry `issued` and `sequence`, because a recording of a genuine evacuation order is
still a genuine evacuation order the second time it is played. A station accepts a
broadcast only if it is newer than the last one it accepted from that authority.
"""

from .situation import BitReader, BitWriter

BROADCAST_VERSION = 2          # reports are version 1; this is how the two are told apart
HEADER_BITS = [("version", 3), ("kind", 2), ("issued", 22), ("sequence", 9), ("spare", 4)]

ORDER, DIGEST = 0, 1

ACTIONS = [
    "evacuate now",
    "shelter in place",
    "boil water before drinking",
    "collection point open",
    "medical team on the way",
    "supplies on the way",
    "road reopened",
    "send a report now",
    "stand down",
    "hold for further instructions",
    "move to higher ground",
    "do not travel",
    "reserved",
    "reserved",
    "reserved",
    "reserved",
]

SCOPES = ["everyone", "shelter", "zone"]

# how far into the past a broadcast may claim to have been issued before it is treated as
# a recording being played back rather than a fresh instruction
STALE_AFTER_MIN = 180

MAX_DIGEST_ENTRIES = 40


def _header(kind, issued, sequence):
    writer = BitWriter()
    for name, bits in HEADER_BITS:
        writer.write({"version": BROADCAST_VERSION, "kind": kind, "issued": issued,
                      "sequence": sequence, "spare": 0}[name], bits)
    return writer.to_bytes()


def is_broadcast(payload):
    """Tell a broadcast from a situation report by the version in the leading bits."""
    return bool(payload) and (payload[0] >> 5) == BROADCAST_VERSION


def encode_order(issued, sequence, action, scope="everyone", target=0, within_hours=63):
    if action not in ACTIONS or ACTIONS[ACTIONS.index(action)] == "reserved":
        raise ValueError(f"unknown action {action!r}")
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; choose from: {', '.join(SCOPES)}")

    body = BitWriter()
    body.write(SCOPES.index(scope), 2)
    body.write(target, 12)
    body.write(ACTIONS.index(action), 4)
    body.write(within_hours, 6)

    return _header(ORDER, issued, sequence) + body.to_bytes()


def encode_digest(issued, sequence, holdings):
    """`holdings` is a sequence of (shelter, minutes) - the newest the base has of each.

    Ages are stored relative to the moment of issue, so twelve bits covers nearly three
    days and each entry costs three bytes rather than five. The count is eight bits rather
    than the six it needs, so that the body lands on a byte boundary without padding.
    """
    entries = [(shelter, issued - minutes) for shelter, minutes in holdings
               if 0 <= issued - minutes < (1 << 12)][:MAX_DIGEST_ENTRIES]

    body = BitWriter()
    body.write(len(entries), 8)
    for shelter, age in entries:
        body.write(shelter, 12)
        body.write(age, 12)

    return _header(DIGEST, issued, sequence) + body.to_bytes()


def decode(payload):
    reader = BitReader(payload)
    fields = {name: reader.read(bits) for name, bits in HEADER_BITS}

    if fields["version"] != BROADCAST_VERSION:
        raise ValueError(f"not a broadcast: version {fields['version']}")

    message = {"kind": fields["kind"], "issued": fields["issued"],
               "sequence": fields["sequence"]}

    if fields["kind"] == ORDER:
        message["scope"] = SCOPES[reader.read(2)]
        message["target"] = reader.read(12)
        message["action"] = ACTIONS[reader.read(4)]
        message["within_hours"] = reader.read(6)

    elif fields["kind"] == DIGEST:
        count = reader.read(8)
        message["holdings"] = [
            (reader.read(12), fields["issued"] - reader.read(12)) for _ in range(count)
        ]

    else:
        raise ValueError(f"unknown broadcast kind {fields['kind']}")

    return message


def describe(message):
    if message["kind"] == ORDER:
        who = {"everyone": "everyone",
               "shelter": f"shelter {message['target']}",
               "zone": f"zone {message['target']}"}[message["scope"]]
        when = "" if message["within_hours"] == 63 else \
            f", within {message['within_hours']} hour{'' if message['within_hours'] == 1 else 's'}"
        return f"ORDER to {who}: {message['action']}{when}"

    return f"the base holds reports from {len(message['holdings'])} shelter(s)"


class Bulletin:
    """What a station believes the authority has said, and refuses to be told twice.

    A recording of a real order is still correctly signed. Freshness is what separates an
    instruction from a replay, so the signature is necessary and not sufficient.
    """

    def __init__(self, public_bytes, now_minutes=None):
        self.public_bytes = public_bytes
        self.now = now_minutes
        self.newest = None
        self.latest_order = None

    def accept(self, payload, signature, now_minutes=None):
        from .trust import Authority

        if not is_broadcast(payload):
            return None, "not a broadcast"

        if not Authority.verify(self.public_bytes, payload, signature):
            return None, "signature does not verify"

        message = decode(payload)
        stamp = (message["issued"], message["sequence"])
        now = now_minutes if now_minutes is not None else self.now

        if now is not None and message["issued"] < now - STALE_AFTER_MIN:
            return None, f"issued {now - message['issued']} minutes ago; treating as a replay"

        if self.newest is not None and stamp <= self.newest:
            return None, "already seen this one, or something newer"

        self.newest = stamp
        if message["kind"] == ORDER:
            self.latest_order = message

        return message, None
