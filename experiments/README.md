# experiments — the evidence

Nothing here is needed to run SoundOut. Everything here is why the design is the way it is.

Each file answers one question with a number, and the numbers are what `docs/JOURNAL.md`
is written from. Several of them exist because a decision that seemed obvious turned out to
be wrong when it was finally measured — which is the point of keeping them runnable rather
than writing the results down once and moving on.

Run any of them directly:

```bash
python -m experiments.selftest
```

## Does the thing work at all?

| file | the question it answers |
|---|---|
| `selftest.py` | Do the tones survive noise, and at what point does detection fall apart? |
| `synctest.py` | Does the chirp and matched filter actually find the start of a transmission, and how much better is it than the energy threshold it replaced? |
| `schematest.py` | Does the 12-byte schema round-trip, does the HMAC tag reject forgeries, and what did packing the fields save over free text? |
| `storetest.py` | Do two stations that heard different things in different orders arrive at the same picture? |
| `fectest.py` | Does Reed–Solomon repair damaged bytes, and how many can it take before it gives up? |
| `demotest.py` | The whole pipeline end to end at a realistic noise level, including a forgery being turned away. |

## What is each decision worth?

| file | the question it answers |
|---|---|
| `calibrate.py` | Where should the preamble threshold sit? Measures burst-present against pure noise and shows why PSR 8.0. |
| `fecgain.py` | How much noise does error correction buy, and what does it cost in airtime? |
| `rangegain.py` | What do the slower modes actually gain — and it was not what the theory predicted until the preamble was scaled too. |
| `radiohop.py` | What does a handheld radio do to the signal, and does the VOX wake-up tone matter? Also contains the measurement that killed a feature. |
| `relaytest.py` | Is passing reports on worth it, how does delivery grow with time, and what happens when every station answers at once? |
| `authoritytest.py` | Can a signed order be forged, altered or replayed — and does the digest save more airtime than it costs? |
| `comparison.py` | Against a runner, a phone network and nothing at all, how old is the information the base is acting on? |

## Supporting

| file | what it is for |
|---|---|
| `chart.py` | Draws `docs/comparison.svg` by hand. No plotting library — the project asks for three dependencies and a chart drawn once a weekend does not justify a fourth. |
| `response.py` | Sweeps your actual speaker and microphone to find where they are loudest, and says whether moving the tones would pay. **Needs hardware and has not been run yet.** |

## The interesting failures

These are worth reading before trusting any measurement you write yourself.

**`fecgain.py` measured nothing at all**, silently, because changing a module-level constant
did not affect functions that had already bound it as a default argument. The tell was the
airtime column: identical to the hundredth of a second at every setting. A control that
cannot possibly stay constant is how you find out your experiment is not connected to
anything.

**`rangegain.py` disagreed with the theory** — the slow modes bought +1 dB where +3 was
predicted. Separating the two failure paths, preamble-not-found from data-not-decoded,
showed the payload decoding 100% of the time it was heard at all. The bottleneck had moved
to the fixed-length chirp. Scaling the preamble with the mode gave the predicted gain.

**`radiohop.py` contains a feature that was measured and deleted.** A radio keying up makes
a broadband crack, so the theory was that it could outrank the chirp and steal the sync.
The fix was built, the threshold re-calibrated, and then it never helped once across three
scenarios — a matched filter accumulates the chirp coherently while an impulse only grows
as a square root. The code was reverted and the measurement kept.

**`relaytest.py` had three faults in the model before any number meant anything.** The
baseline gave each shelter a single transmission, which nobody would do. The simulation had
no carrier sense while the real relay waits for quiet — it was measuring a protocol that
had not been built. And the theoretical ceiling came out *below* the measured result, which
is impossible, because it counted only reliable links.

**`comparison.py` was flattering itself.** Every report re-rolled the delivery odds, so
across 144 reports even a shelter connected to nothing succeeded eventually by repetition.
A stranded shelter is stranded permanently, not unlucky repeatedly.

**`authoritytest.py` printed a claim its own numbers contradicted** — that the digest paid
for itself, directly beneath a figure showing it losing half a second. The error was
measuring one relay when a digest is heard by every station at once.
