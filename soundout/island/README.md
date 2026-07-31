# soundout/island — what the sound is actually saying

`soundout/radio` moves bytes. This layer decides what those bytes mean: what a shelter can
say in twelve of them, who is allowed to say it, what to do with a report once it arrives,
and what to pass on to somebody else.

| file | what it is for |
|---|---|
| `situation.py` | The 12-byte schema. Bit-packs a whole shelter report — occupancy, needs, casualties, road access, timestamp — and reads it back. Also `describe()`, which turns one into a sentence. |
| `trust.py` | Who said this. HMAC tags for shelter reports (4 bytes) and Ed25519 for the base's broadcasts (64 bytes), plus the demo keys that make the whole thing reproducible. |
| `reports.py` | Building a report, checking its tag, and `ingest()` — the one entry point that takes audio and does the right thing with whatever comes out of it. |
| `store.py` | Where observations live. A grow-only set keyed on the report's own bytes, with the current picture as a deterministic fold over it. Migrates itself when the schema grows. |
| `relay.py` | Which observations to pass on, in what order, and when to stop. The urgency ranking and the once-each rule live here. |
| `authority.py` | Messages going the other way: signed orders and digests, and the freshness rules that stop a recording being replayed as an instruction. |
| `validate.py` | Every input rule in one place, so a typo becomes a readable message rather than a stack trace or a corrupt report. |

## The twelve bytes

```
version 3 | reporter 13 | shelter 12 | occupancy 10 | capacity 10
needs 12  | casualties 7 | access 3  | minutes 22   | reserved 4
```

Ninety-six bits exactly. Free text was the first thing tried and it was the wrong answer:
it took several times the airtime and could not be checked, sorted or merged.

## Two tiers of trust, and why they differ

| | reports | broadcasts |
|---|---|---|
| from | a shelter | the emergency office |
| proves | this came from shelter 37 | this came from the base |
| costs | **4 bytes** | **64 bytes** |
| why | a shared secret between one shelter and the base | a signature everyone can check and nobody can write |

A shelter must be able to *verify* an evacuation order without holding anything that would
let it *write* one. A shared HMAC key cannot do that — a secret good enough to check a
message is good enough to forge one — which is the entire reason for the sixteenfold size
difference.

## Typical use

```python
from soundout.island.reports import build_report, ingest
from soundout.island.store import Store
from soundout.radio.link import transmit

payload = build_report(reporter=1041, shelter=37, people=42, capacity=60,
                       needs=["water", "insulin"], casualties=2, access="impassable")

store = Store("soundout.db")
outcome = ingest(transmit(payload), store)      # decode, authenticate, store
outcome["authentic"], outcome["description"]

store.view()        # the current picture, one row per shelter
store.summary()     # totals, who is full, who is cut off, what is needed most
```

Passing something on, and being told to stop:

```python
from soundout.island import relay

waiting = relay.pending(store)                  # worst first
payload = relay.payload_of(waiting[0])          # the original bytes, tag included
relay.mark_relayed(store, waiting[0])           # once each is what makes it terminate

relay.suppress(store, digest["holdings"])       # the base already has these
```

Checking an order before obeying it:

```python
from soundout.island import authority
from soundout.island.trust import Authority

bulletin = authority.Bulletin(Authority.demo().public_bytes())
message, error = bulletin.accept(body, signature)
```

## Things worth knowing before changing anything here

**The store is a grow-only set and the picture is a fold over it.** Nothing is ever updated
in place, so it does not matter how many times a report bounces around the island or in
what order things arrive — every station that has heard the same reports computes the same
picture. This is what makes relaying safe.

**A relay forwards the original bytes, tag and all.** It never re-signs. That is why the
store keeps the tag, and why observations recorded before the tag was stored are never
relayed: you cannot pass on what you cannot prove.

**A valid signature is not enough.** A recording of a genuine evacuation order verifies
perfectly. `Bulletin` refuses anything it has already seen, and anything claiming to be
more than three hours old.
