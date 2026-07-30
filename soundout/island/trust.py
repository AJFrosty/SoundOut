import hashlib
import hmac
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

TAG_BYTES = 4
SIGNATURE_BYTES = 64

DEMO_MASTER = b"soundout-demo-master-key-not-for-real-use"

# The emergency office's signing key. In use this is generated once, kept offline, and
# only its public half is distributed - printed on the back of every receiver, handed out
# before the season. Fixed here so the demonstration is reproducible.
DEMO_AUTHORITY_SEED = b"soundout-demo-authority-seed-not-real!!!"[:32]


def derive_key(reporter_id, master=DEMO_MASTER):
    return hmac.new(master, reporter_id.to_bytes(2, "big"), hashlib.sha256).digest()


def new_shelter_key():
    return os.urandom(32)


def tag(report, key):
    digest = hmac.new(key, report, hashlib.sha256).digest()
    return digest[:TAG_BYTES]


def verify_tag(report, received, key):
    return hmac.compare_digest(tag(report, key), received)


def forgery_odds():
    return 1 / (1 << (TAG_BYTES * 8))


class ShelterKeys:
    def __init__(self):
        self.keys = {}

    def issue(self, reporter_id):
        self.keys[reporter_id] = new_shelter_key()
        return self.keys[reporter_id]

    def get(self, reporter_id):
        return self.keys.get(reporter_id)

    def authenticate(self, reporter_id, report, received):
        key = self.get(reporter_id)
        if key is None:
            return False, "unknown reporter"
        if not verify_tag(report, received, key):
            return False, "bad authentication tag"
        return True, None


class Authority:
    def __init__(self, private_key=None):
        self.private_key = private_key or Ed25519PrivateKey.generate()

    @classmethod
    def demo(cls):
        return cls(Ed25519PrivateKey.from_private_bytes(DEMO_AUTHORITY_SEED))

    def public_bytes(self):
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, payload):
        return self.private_key.sign(payload)

    @staticmethod
    def verify(public_bytes, payload, signature):
        try:
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, payload)
            return True
        except (InvalidSignature, ValueError):
            return False
