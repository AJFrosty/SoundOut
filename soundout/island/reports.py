from datetime import datetime, timezone

from ..radio.link import receive
from . import authority
from .situation import REPORT_BYTES, decode_report, describe, encode_report
from .trust import SIGNATURE_BYTES, TAG_BYTES, derive_key, tag, verify_tag

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def minutes_now():
    return int((datetime.now(timezone.utc) - EPOCH).total_seconds() // 60)


def build_report(reporter, shelter, people, capacity, needs, casualties, access,
                 minutes=None):
    packed = encode_report(
        reporter=reporter,
        shelter=shelter,
        occupancy=people,
        capacity=capacity,
        needs=needs,
        casualties=casualties,
        access=access,
        minutes=minutes if minutes is not None else minutes_now(),
    )
    return packed + tag(packed, derive_key(reporter))


def authenticate(payload):
    if len(payload) != REPORT_BYTES + TAG_BYTES:
        return None, False, f"expected {REPORT_BYTES + TAG_BYTES} bytes, got {len(payload)}"

    body = payload[:REPORT_BYTES]
    received = payload[REPORT_BYTES:]
    reporter = decode_report(body)["reporter"]

    return body, verify_tag(body, received, derive_key(reporter)), None


def sign_broadcast(body, office):
    return body + office.sign(body)


def _take_broadcast(result, store, bulletin):
    """A broadcast is not stored as an observation; it is an instruction or an answer."""
    payload = result["payload"]

    if len(payload) <= SIGNATURE_BYTES:
        return {"stored": False, "reason": "broadcast too short to carry a signature",
                "burst": result["burst"]}

    body, signature = payload[:-SIGNATURE_BYTES], payload[-SIGNATURE_BYTES:]

    if bulletin is None:
        return {"stored": False, "broadcast": True,
                "reason": "a broadcast arrived but no authority key is configured",
                "burst": result["burst"]}

    message, error = bulletin.accept(body, signature)
    if error:
        return {"stored": False, "broadcast": True, "reason": error,
                "burst": result["burst"]}

    applied = 0
    if message["kind"] == authority.DIGEST and store is not None:
        from . import relay
        applied = relay.suppress(store, message["holdings"])

    return {
        "stored": False,
        "broadcast": True,
        "message": message,
        "description": authority.describe(message),
        "suppressed": applied,
        "burst": result["burst"],
    }


def ingest(signal, store, rate=None, bulletin=None):
    result = receive(signal) if rate is None else receive(signal, rate=rate)

    if not result["ok"]:
        return {"stored": False, "reason": result["error"], "burst": result["burst"]}

    if authority.is_broadcast(result["payload"]):
        return _take_broadcast(result, store, bulletin)

    body, authentic, error = authenticate(result["payload"])
    if error:
        return {"stored": False, "reason": error, "burst": result["burst"]}

    fresh = store.add(body, authenticated=authentic,
                      tag_bytes=result["payload"][REPORT_BYTES:])

    return {
        "stored": True,
        "fresh": fresh,
        "authentic": authentic,
        "report": decode_report(body),
        "description": describe(body),
        "burst": result["burst"],
        "median_margin": result["median_margin"],
    }
