from datetime import datetime, timezone

from ..radio.link import receive
from .situation import REPORT_BYTES, decode_report, describe, encode_report
from .trust import TAG_BYTES, derive_key, tag, verify_tag

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


def ingest(signal, store, rate=None):
    result = receive(signal) if rate is None else receive(signal, rate=rate)

    if not result["ok"]:
        return {"stored": False, "reason": result["error"], "burst": result["burst"]}

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
