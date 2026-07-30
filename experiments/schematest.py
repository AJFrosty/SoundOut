import numpy as np

from soundout.radio.channel import through_simulated_channel
from soundout.radio.link import receive, transmit
from soundout.radio.tones import RATE
from soundout.island.situation import (
    NEEDS,
    REPORT_BYTES,
    decode_report,
    describe,
    encode_report,
    field_limits,
    needs_mask,
)
from soundout.island.trust import (
    SIGNATURE_BYTES,
    TAG_BYTES,
    Authority,
    ShelterKeys,
    forgery_odds,
    tag,
)

RNG = np.random.default_rng(23)

REPORT = dict(
    reporter=1041,
    shelter=37,
    occupancy=42,
    capacity=60,
    needs=["water", "insulin"],
    casualties=2,
    access="impassable",
    minutes=1_234_567,
)

FREE_TEXT = "SHELTER 37 42PPL NO INSULIN ROAD BLOCKED"


def round_trip():
    packed = encode_report(**REPORT)
    back = decode_report(packed)

    print(f"packed size : {len(packed)} bytes")
    print(f"hex         : {packed.hex()}")
    print(f"reads back  : {describe(back)}")

    assert len(packed) == REPORT_BYTES
    assert back["shelter"] == REPORT["shelter"]
    assert back["occupancy"] == REPORT["occupancy"]
    assert back["needs_names"] == REPORT["needs"]
    assert back["access_name"] == REPORT["access"]
    assert back["minutes"] == REPORT["minutes"]
    print("round trip  : every field survived")


def boundaries():
    print("\nfield limits (max value each field can hold)")
    limits = field_limits()
    for name, limit in limits.items():
        print(f"  {name:11s} {limit:>10,}")

    extreme = encode_report(
        reporter=limits["reporter"], shelter=limits["shelter"],
        occupancy=limits["occupancy"], capacity=limits["capacity"],
        needs=needs_mask(NEEDS), casualties=limits["casualties"],
        access=6, minutes=limits["minutes"])

    back = decode_report(extreme)
    assert back["occupancy"] == limits["occupancy"]
    assert len(back["needs_names"]) == len(NEEDS)
    print("  all-maximum report packs and unpacks correctly")

    try:
        encode_report(**{**REPORT, "occupancy": 1024})
        print("  OVERFLOW NOT CAUGHT")
    except ValueError as error:
        print(f"  overflow refused: {error}")


def authentication():
    print("\nauthentication")
    keys = ShelterKeys()
    keys.issue(REPORT["reporter"])

    packed = encode_report(**REPORT)
    authentic = tag(packed, keys.get(REPORT["reporter"]))

    ok, error = keys.authenticate(REPORT["reporter"], packed, authentic)
    print(f"  genuine report      : {'accepted' if ok else 'rejected ' + str(error)}")

    tampered = bytearray(packed)
    tampered[4] ^= 0b00000001
    ok, error = keys.authenticate(REPORT["reporter"], bytes(tampered), authentic)
    print(f"  one bit changed     : {'ACCEPTED - BAD' if ok else 'rejected (' + error + ')'}")

    ok, error = keys.authenticate(999, packed, authentic)
    print(f"  unknown reporter    : {'ACCEPTED - BAD' if ok else 'rejected (' + error + ')'}")

    ok, error = keys.authenticate(REPORT["reporter"], packed, b"\x00\x00\x00\x00")
    print(f"  guessed tag         : {'ACCEPTED - BAD' if ok else 'rejected (' + error + ')'}")
    print(f"  odds of a lucky guess: 1 in {int(1 / forgery_odds()):,}")


def authority_broadcast():
    print("\nauthority broadcast (public key, no shared secret)")
    authority = Authority()
    order = b"EVACUATE ZONE 4 BY 1800"

    signature = authority.sign(order)
    print(f"  signature size      : {len(signature)} bytes")
    print(f"  genuine order       : "
          f"{'verified' if Authority.verify(authority.public_bytes(), order, signature) else 'FAILED'}")

    faked = b"EVACUATE ZONE 9 BY 1800"
    print(f"  altered order       : "
          f"{'ACCEPTED - BAD' if Authority.verify(authority.public_bytes(), faked, signature) else 'rejected'}")

    impostor = Authority()
    print(f"  impostor signature  : "
          f"{'ACCEPTED - BAD' if Authority.verify(authority.public_bytes(), order, impostor.sign(order)) else 'rejected'}")


def airtime():
    print("\nairtime: the same information, three ways")

    text_audio = len(transmit(FREE_TEXT)) / RATE
    report_audio = len(transmit(encode_report(**REPORT))) / RATE
    authed = len(transmit(encode_report(**REPORT) + b"\x00" * TAG_BYTES)) / RATE
    signed = len(transmit(encode_report(**REPORT) + b"\x00" * SIGNATURE_BYTES)) / RATE

    print(f"  free text, {len(FREE_TEXT):3d} bytes      : {text_audio:5.2f} s")
    print(f"  schema,    {REPORT_BYTES:3d} bytes      : {report_audio:5.2f} s  "
          f"({text_audio / report_audio:.1f}x faster, and machine readable)")
    print(f"  schema + 4-byte tag     : {authed:5.2f} s  <- what a field report costs")
    print(f"  schema + 64-byte sig    : {signed:5.2f} s  <- why reports are not signed this way")


def over_the_channel(trials=30):
    print(f"\nsigned reports through the channel ({trials} trials per level)")
    keys = ShelterKeys()
    keys.issue(REPORT["reporter"])

    packed = encode_report(**REPORT)
    payload = packed + tag(packed, keys.get(REPORT["reporter"]))

    print("  SNR dB   delivered   authenticated")

    for snr in (10, 0, -5, -10):
        delivered = 0
        authenticated = 0

        for _ in range(trials):
            signal = transmit(payload)
            padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])
            received = through_simulated_channel(padded, snr, RNG)

            result = receive(received)
            if not result["ok"]:
                continue

            delivered += 1
            body = result["payload"][:REPORT_BYTES]
            received_tag = result["payload"][REPORT_BYTES:]
            reporter = decode_report(body)["reporter"]

            ok, _ = keys.authenticate(reporter, body, received_tag)
            if ok:
                authenticated += 1

        print(f"  {snr:6d}   {delivered / trials:9.0%}   {authenticated / trials:13.0%}")


if __name__ == "__main__":
    round_trip()
    boundaries()
    authentication()
    authority_broadcast()
    airtime()
    over_the_channel()
