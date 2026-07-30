# SoundOut — design journal

Moving structured disaster reports over sound, so an island can share a situation
picture when towers and power are down.

---

## Weekend 1 — can we get a tone out and reliably detect it?

**Goal:** prove the signal path exists before building anything on top of it. If a tone
cannot be recovered, nothing else matters.

### Design decisions and why

**4-FSK, not 2-FSK or 8-FSK.** Four tones carry 2 bits per symbol. Two tones would halve
the rate for no robustness gain that matters here; eight tones would need either wider
spacing (pushing tones outside the usable voice band) or tighter spacing (raising the
chance of confusing neighbours under noise). Four is the point where the tones stay far
apart *and* inside the band that radios and phones actually pass.

**50 baud, 20 ms per symbol.** Deliberately slow. This is not a file transfer — a full
situation report is 12 bytes, which at 100 bps takes about one second. Spending a long
window on each symbol is what buys noise immunity, because the detector integrates over
882 samples.

**Tones at 1000 / 1200 / 1400 / 1600 Hz.** Two constraints decided this:

1. They must sit inside roughly 300–3400 Hz, the range a voice channel and a handheld
   radio will pass. Anything outside is filtered away before it reaches the far end.
2. They must be *orthogonal over one symbol*. With a 20 ms window the frequency
   resolution is 1/0.02 s = 50 Hz, so tones must be whole multiples of 50 Hz apart. The
   200 Hz spacing chosen is 4 bins — comfortably clear of each other.

**Goertzel, not an FFT.** We only care about four known frequencies, so computing a whole
spectrum is wasted work. Goertzel evaluates a single DFT bin as a second-order IIR
resonator: one multiply and two adds per sample, no complex arithmetic, O(N) per tone with
almost no memory. That matters because this has to run on a cheap phone, and later
possibly a microcontroller. An FFT would compute 441 bins to answer a 4-bin question.

**Bin alignment.** With rate 44100 and N = 882 samples, bin spacing is exactly 50 Hz.
Every chosen tone divides evenly: 1000/50 = 20, 1200/50 = 24, 1400/50 = 28, 1600/50 = 32.
Each tone therefore lands dead centre of a bin, so no energy leaks into its neighbours.
Measured: with 1200 Hz sent, the other three detectors report **0.00000**. If the tones
were misaligned, each would smear across neighbouring bins and the margin would collapse.

### What was measured

Amplitude recovery is exact — send 0.5, measure 0.500 — which confirms the normalisation
`A = 2·sqrt(power)/N` is right.

Symbol accuracy against white noise, 200 trials per level, random tone and random phase:

| SNR | accuracy | median margin over runner-up |
|---|---|---|
| +10 dB | 100.0% | 53× |
| 0 dB | 100.0% | 17× |
| −10 dB | 100.0% | 5.1× |
| −15 dB | 100.0% | 3.1× |
| −20 dB | 87.0% | 1.8× |
| −23 dB | 59.5% | 1.3× |
| −30 dB | 35.5% | 1.3× |

Chance is 25%, so it degrades to noise by −30 dB. **Reliable to about −15 dB**, meaning
the tone can be considerably quieter than the noise around it and still be read.

That is not luck, it is processing gain. The detector's noise bandwidth is one bin, 50 Hz,
against a 22 kHz signal band — a ratio of about 26 dB. So at −15 dB input SNR the
in-bin SNR is still around +11 dB, which is comfortable. Theory and measurement agree,
which is the real reason to trust the number.

### The failure that mattered

Pushing 40 symbols through a simulated channel (random delay, random gain, smoothing,
clipping, added noise) gave 0 errors at 15 dB — and **72.5% errors at 5 dB**.

The instinct is "the detector broke". It did not. The clue was in the diagnostics: the
start of the burst was reported at sample 0, and the decoded string contained the sent
string *shifted*. The energy-threshold start detector was tripping on the noise floor
instead of the first tone, so every 20 ms window straddled two symbols.

Proved it by decoding the identical recording from the known true offset:

| SNR | sync method | errors |
|---|---|---|
| 5 dB | energy threshold | 72.5% |
| 5 dB | true offset | **0%** |
| 0 dB | true offset | **0%** |
| −5 dB | true offset | **0%** |

Same signal, same detector, only the alignment differs. **Synchronisation is the whole
problem, not detection.** The timing test says the same thing more gently: accuracy holds
to a 5 ms window error and falls apart by 10 ms, which is half a symbol.

### What this changes

The next real piece of work is not a faster detector, it is a **preamble**: a known
sequence at the head of every burst, found by cross-correlation rather than by energy.
Correlation looks for a *shape*, so it is not fooled by loud noise the way a threshold is.
That was already planned for week 3; this moves it to week 2, because nothing built on top
of a bad start index can work.

### Independently re-run

Every test above was re-run from a clean terminal and reproduced: rejection at 0.00000,
100% accuracy to −15 dB, 0/40 errors on the clean channel, 82.5% errors on the noisy one
with the start detected at sample 0, and 0/40 on the identical noisy signal decoded from
the true offset with a 28× margin. Different random draws, same conclusions.

**Audio output confirmed working** — `play.py` produced an audible warbling chirp through
the speakers. Python → sound card → speakers → air is proven. Capture is the only part of
the hardware chain still untested.

### Still unproven

The real sound card path has not run yet. Both inputs on this machine return absolute
silence: Stereo Mix is disabled in Windows (its default), and nothing is plugged into the
front mic jack. The DSP is verified; the hardware hop is not. To unblock: enable Stereo
Mix under Sound settings → Recording → show disabled devices, or plug in any headset, then
run `loopback.py` with no `--simulate` flag.

---

## Weekend 2 — knowing when to start listening

**Goal:** fix the failure weekend 1 exposed. The detector was fine; finding the beginning
of a burst was not.

### Why the old method could never work

Listening for loudness asks "is the signal here yet?" — a question noise answers wrongly.
When static is as loud as the tones, the first block of static looks exactly like the
start of a transmission. There is no threshold that fixes this, because the thing being
measured carries no information about *what* is loud.

### What replaced it

A **chirp**: a 100 ms tone sweeping from 800 Hz to 2400 Hz, sent ahead of every burst, and
found by **cross-correlation** rather than by level.

Correlation asks a different question: "how well does this stretch of audio match the
shape I am looking for?" Noise is random, so it matches a rising sweep only by accident,
and only weakly. The sweep matches itself enormously at exactly one alignment.

This is a **matched filter**, the same principle radar uses to find an echo buried under
noise. It is provably the optimal detector for a known waveform in white noise. Two
properties matter here:

- **Processing gain.** The chirp is 4410 samples long, so the correlator sums 4410
  opportunities to agree. Random noise partially cancels in that sum; the true sweep does
  not.
- **A sharp peak.** Because the frequency changes throughout, the sweep only matches
  itself at one offset. A steady tone would correlate well at many offsets and give a
  blurry answer — sweeping is what makes the peak narrow.

Correlation is done by FFT (multiply spectra, transform back) rather than by sliding the
template sample by sample, which turns an O(N·M) job into O(N log N).

### The measurement

Error in locating the burst, in samples, median of 40 trials:

| SNR | energy threshold | matched filter |
|---|---|---|
| +20 dB | 104 | **0** |
| +10 dB | 25,008 | **0** |
| +5 dB | 25,116 | **0** |
| 0 dB | 25,676 | **0** |
| −5 dB | 24,902 | **0** |
| −10 dB | 25,310 | **0** |

Zero. Not "small" — sample-exact, every trial, down to −10 dB where the noise is ten times
the power of the signal. The old method is off by about 25,000 samples, which is half a
second: it is not finding the burst at all, it is triggering on the noise floor.

### A frame, not just symbols

With sync solved, bytes became possible. Each symbol carries 2 bits, so a byte is 4
symbols. A frame is now:

```
[ chirp ][ guard ][ length ][ ...payload... ][ crc8 ]
```

The length byte tells the receiver how much to read, and the CRC tells it whether what it
read is trustworthy. Delivering the 40-byte message
`SHELTER 37 42PPL NO INSULIN ROAD BLOCKED`, 40 trials per level:

| SNR | delivered intact | caught by CRC | preamble missed |
|---|---|---|---|
| +10 dB | 100% | 0% | 0% |
| 0 dB | 100% | 0% | 0% |
| −10 dB | 100% | 0% | 0% |
| −15 dB | 65% | 35% | 0% |

Corruption test: 200 frames deliberately damaged mid-burst, **0 slipped past the CRC**.
Nothing was accepted as good when it was not.

### The honest reading of −15 dB

Per-symbol accuracy at −15 dB is essentially perfect, yet only 65% of *messages* arrive.
There is no contradiction: this message is 168 symbols, and every one must be right.
Even 99.7% per symbol gives 0.997¹⁶⁸ ≈ 60% per frame. **Symbol accuracy compounds.**

The CRC is currently doing the honest thing — refusing bad frames rather than passing
corrupted text to an agent. But refusing is not recovering. That is precisely the argument
for forward error correction later: with FEC, the frames now being rejected at −15 dB
become frames that arrive correct, because a handful of wrong symbols can be repaired
rather than being fatal.

### Airtime

For a 40-byte message: 3.48 s total, of which 0.12 s preamble, 0.16 s length and CRC,
3.20 s payload — **92% useful**. Which is also the argument for the structured 12-byte
schema over free text: the same information as a form would be about one second.

### End to end

`message.py` now sends and decodes real text. Written to a wav and read back, the exact
sentence returns, preamble prominence 31.7×.

---

## Weekend 3 — a report that fits, and cannot be faked

**Goal:** stop sending sentences. Send a structured report, and prove who sent it.

### The 12-byte schema

Free text was never the plan; it was scaffolding. Emergency information is mostly numbers
and checkboxes, so it should be sent as numbers and checkboxes. Ninety-six bits, packed:

| field | bits | holds |
|---|---|---|
| version | 3 | 8 revisions of this format |
| reporter | 13 | 8,191 devices |
| shelter | 12 | 4,095 shelters |
| occupancy | 10 | 0-1,023 people |
| capacity | 10 | 0-1,023 places |
| needs | 12 | twelve flags: water, food, insulin, dialysis, baby formula, fuel, tarpaulin, medic, evacuation, sanitation, comms, power |
| casualties | 7 | 0-127 |
| access | 3 | open, debris, impassable, flooded, bridge down, landslide, unknown |
| minutes | 22 | timestamps for eight years |
| reserved | 4 | room to grow |

The bit writer refuses anything that does not fit rather than silently truncating: asking
for occupancy 1024 in a 10-bit field raises, it does not quietly send 0. A field that
overflows in silence would put a wrong number in front of an agent, which is worse than
sending nothing.

`24110250a83c0050492d6870` decodes to *"Shelter 37: 42 of 60 places used, needs water,
insulin, 2 casualties, access impassable"*.

### Why reports are not signed with a public key

The obvious move is Ed25519 on every report. The numbers say no:

| what is sent | airtime |
|---|---|
| free text, 40 bytes | 3.48 s |
| schema, 12 bytes | 1.24 s |
| schema + 4-byte tag | **1.56 s** |
| schema + 64-byte Ed25519 signature | 6.36 s |

A signature four times larger than the message would spend 80% of the airtime proving who
sent it. On a channel this narrow that is not a security decision, it is a denial of
service against yourself.

So authentication is tiered by what the threat actually is:

- **Field reports** carry a **4-byte truncated HMAC-SHA256** against a key issued to the
  shelter when it is set up. Odds of a blind forgery: 1 in 4,294,967,296. Cost: 0.32 s.
- **Authority broadcasts** — evacuation orders, the messages where a forgery gets people
  killed — are signed with **Ed25519**. They are rare, they go to everyone, and there is
  no shared secret for a looter to steal from a captured handset. 6.36 s is affordable a
  few times a day.

Tested: a genuine report is accepted; one flipped bit is rejected; an unknown reporter is
rejected; a guessed tag is rejected. A genuine order verifies; an altered order and an
impostor's signature are both rejected.

### The regression I introduced, and the real lesson

Weekend 2's detector reported a "prominence" that turned out to be uncomparable between
recordings — it divided by the median of the whole file, so a mostly-silent recording
scored 34,000 and a mostly-data one scored 32. Replacing it with a **normalised
correlation coefficient** fixed comparability and broke detection.

At −10 dB, delivery went from 100% to **0%**.

The coefficient is bounded by the noise. For signal and noise mixed at ratio SNR, the best
achievable correlation with a clean template is about sqrt(SNR/(1+SNR)):

| SNR | predicted | measured |
|---|---|---|
| 0 dB | 0.707 | 0.678 |
| −10 dB | 0.30 | 0.279 |
| −15 dB | 0.175 | 0.157 |

The threshold had been set at 0.30 — a value that is *mathematically unreachable* at
−10 dB. It passed every test on clean files and could never have worked in the field.

The mistake was conflating two different questions:

- **"Is a burst here?"** — a detection decision, which must be made against the noise in
  *this* recording.
- **"How good is it?"** — a quality measure, which should be comparable across recordings.

They need different statistics. Detection now uses **peak-to-sidelobe ratio**: how far the
correlation peak stands above everything else, in standard deviations. Quality is still
reported as the correlation coefficient, but nothing is decided on it.

Calibrated rather than guessed:

| | burst present (worst of 40) | pure noise (worst of 40) |
|---|---|---|
| −10 dB | PSR 19.7 | — |
| −15 dB | PSR 10.5 | — |
| noise only | — | PSR 7.2 |

A threshold of 8.0 sits in the gap: **100% detection down to −15 dB, zero false alarms on
pure noise, and the located start is still sample-exact.** At −20 dB the distributions
overlap (burst 5.6, noise 7.2) — that is the honest limit of this preamble, not a tuning
problem.

### End to end

Authenticated 12-byte reports through the simulated channel, 30 trials per level:

| SNR | delivered | authenticated |
|---|---|---|
| +10 dB | 100% | 100% |
| 0 dB | 100% | 100% |
| −5 dB | 100% | 100% |
| −10 dB | 100% | 100% |

A real situation report now costs **1.56 seconds of airtime**, arrives intact where the
noise is ten times the signal, and cannot be altered or forged without the shelter's key.

---

## Weekend 3, part 2 — it left the computer

First transmission over real air rather than simulation.

A signed 16-byte report was played through a headset earpiece, captured by that headset's
microphone, and decoded exactly:

```
heard : peak 0.0612
sync  : FOUND (PSR 26.3 of 8.0 needed, match 0.975)
ok    : 16 bytes recovered, margin 76.0x
report: Shelter 37: 42 of 60 places used, needs water, insulin,
        2 casualties, access impassable
exact : True
```

PSR 26.3 against a threshold of 8.0, and a correlation of 0.975. Real air with a cheap
headset was barely harder than the simulated channel — the threshold calibrated against
simulated noise held up in the physical world, which is the useful part.

### Three failures on the way, all instructive

**The harness fought the library.** `sounddevice`'s module-level `play()` and `rec()` share
one global stream, so starting playback silently stopped the recording a thread had begun.
Every result read "recorded silence" while the hardware was fine. Fixed by using `playrec`,
a single duplex stream. This is the reason the earlier `audiocheck` verdicts could not be
trusted either.

**Host APIs cannot be mixed.** PortAudio refuses a duplex stream whose input and output
sit on different host APIs — `Illegal combination of I/O devices`. Stereo Mix is WDM-KS
while the speakers were MME. Input and output now have to be chosen as a matching pair.

**Nothing was coming out of the speakers.** With headphones in the jack, Windows mutes the
speaker device, so the first air test played into a muted output and the microphone heard
only the room: peak 0.0219, match 0.051, which is indistinguishable from noise. Playing to
the headphone output instead moved match from 0.051 to 0.975. The bug was in the routing,
not the radio.

### The old sync failed again, in public

`loopback.py` still carries the weekend 1 energy-threshold sync, and over real air it
failed exactly as it did in simulation — 82.5% symbol errors, with the decoded string
being the sent string shifted by four symbols. It had triggered about 80 ms early on room
noise.

The same audio path, with a chirp preamble and matched filter in front of it, decodes
perfectly. Simulation predicted the failure and the fix, and the hardware agreed with
both.

---

## Weekend 4 — from packets to a picture

**Goal:** stop treating reports as messages. Twenty shelters shouting once each has to
become one island picture, and it has to be the *same* picture on every device regardless
of what each one happened to hear, or in what order.

### The design decision that makes this easy

The tempting model is a table of shelters that gets updated as reports arrive. That model
fights the problem: whether shelter 37 currently reads 42 or 51 people then depends on
which report landed last, which depends on who walked past whom.

Instead the store is **a grow-only set of signed observations**, and the situation picture
is a **deterministic fold over that set**:

```
observations  →  (pick newest per shelter)  →  the picture
```

Insertion is keyed on the raw 12 bytes, so hearing the same report five times inserts one
row. The picture is computed, never mutated. Convergence is not something the merge logic
has to be careful about — it is a property of taking a maximum over a set, which cannot
depend on order.

This is the CRDT idea, but arrived at from the shape of the problem rather than imported:
a grow-only set (G-Set) of observations, with a last-writer-wins register per shelter
derived from it, ordered by `(minutes, reporter)` so ties break the same way everywhere.

### Proved rather than asserted

| property | result |
|---|---|
| order independence | 200 random orderings of 24 reports, **200/200 identical** |
| idempotence | hearing every report three times equals hearing it once |
| newest wins | out-of-order arrival still leaves the latest occupancy showing |
| tie break | identical timestamps resolve identically in all 6 permutations |
| forged data quarantined | unauthenticated reports never enter the trusted picture |

The tie-break test matters more than it looks. Two shelters reporting in the same minute is
not unusual, and without a deterministic second key the two devices would disagree forever
while both being "correct".

### The aggregate an agent actually wants

Needs are ranked by **people affected**, not by report count — one full 180-place shelter
needing water outranks three small ones. From three shelters:

```
256 people across 3 shelters, 4 casualties
cut off: [37]   full: [12]
needs: water (231), food (180), insulin (76), fuel (51), medic (25)
```

That last line is the reason the schema exists. Twenty voice reports could never produce
it without someone transcribing them by hand.

### End to end, through a noisy channel

Four reports were transmitted as audio through a 5 dB channel in a shuffled order and
decoded, authenticated and merged with no other input. Shelter 37 reported twice — 42
people, then 51 — and the assembled picture shows 51 whichever order the two arrived in.

### The forgery case

A looter with a stolen handset transmits a report claiming shelter 37 is empty, with a
newer timestamp so it would win on recency alone:

```
trusted picture   : 42 people (the genuine report)
if unverified were included: 0 people (the forgery)
both kept — 2 observations on record — only the authenticated one counts
```

The forgery is not discarded, it is quarantined. Deleting it would destroy evidence that
someone is transmitting false reports, which is itself information the authorities want.

### The demo loop now exists

`report.py` composes and transmits a report from the command line. `receiver.py` listens
continuously, decodes, authenticates and merges into SQLite. `dashboard.py` serves the
island picture on localhost with no dependencies beyond the standard library, refreshing
every two seconds.

---

## Weekend 5 — repairing damage instead of discarding it

**Goal:** the CRC could only ever say "this is broken". Reed-Solomon repairs a few wrong
bytes so the frame survives, which is what buys range on a worse channel.

### Why Reed-Solomon over GF(256) suits this channel exactly

Four symbols make one byte. A misread tone therefore damages **exactly one byte**, however
many of its bits are wrong. Reed-Solomon corrects *byte* errors wherever they fall, so the
code and the channel line up without any cleverness: t bad tones cost t bad bytes, and
2t parity bytes repair them.

It also handles bursts for free. A squelch click that wipes three consecutive symbols
damages three consecutive bytes, and the decoder does not care whether errors are spread
out or adjacent.

### Built and checked in stages

The field first, because everything stands on it and a broken field fails in ways that
look like decoder bugs. GF(256) was verified to actually be a field: closure, identity,
an inverse for every nonzero element, commutativity, associativity, distributivity, and
division undoing multiplication.

Then encoding, then decoding, measured at each step:

| bytes damaged | recovered | detected as too damaged | wrong answer |
|---|---|---|---|
| 0 | 100% | 0% | 0% |
| 1 | 100% | 0% | 0% |
| 2 | 100% | 0% | 0% |
| 3 (the limit) | 100% | 0% | 0% |
| 4 | 0% | 100% | 0% |
| 5 | 0% | 100% | 0% |

Exactly the theoretical behaviour: six parity bytes correct three errors, and beyond that
it refuses rather than guessing. Consecutive damage behaves identically, as expected.

### The bug that produced a plausible-looking wrong answer

The first run corrected nothing at all — every single-byte error came back as "too
damaged". The field tests all passed, which localised it immediately: the fault had to be
in the error locator, not the arithmetic.

Feeding one known error through by hand gave a locator of `[76, 0]`. A valid error locator
must satisfy Λ(0) = 1, so a zero constant term is impossible — the polynomial was
malformed rather than merely wrong. Two mistakes in Berlekamp-Massey:

1. the discrepancy was computed *after* shifting the previous polynomial rather than
   before, so it used the wrong syndrome alignment;
2. the update step was skipped in the branch where the polynomials swap.

Both are single lines. With them fixed the locator became `[76, 1]`, the Chien search
found position 5, and it has corrected everything within its limit since.

Worth noting what did *not* happen: it never produced a wrong answer, even while broken.
It failed closed.

### The experiment that measured nothing

The first attempt at "does FEC help" varied the parity level by reassigning
`framing.PARITY_BYTES` between runs. The output looked believable — three columns, small
differences — until the airtime column read **2.20 s for every configuration**. Adding
parity bytes must add airtime, so the numbers could not be real.

The cause is that `def build_frame(payload, parity_bytes=PARITY_BYTES)` binds its default
**when the function is defined**, not when it is called. Reassigning the module attribute
afterwards changes nothing. All three columns had run the identical configuration and the
differences were random noise.

Parity is now a parameter threaded through `transmit` and `receive`. The lesson is that
the airtime column was doing real work as a control: a number that *must* change if the
experiment is valid, sitting next to the numbers being measured.

### What the protection actually buys

Delivery of a 16-byte authenticated report, 40 trials per level:

| SNR | crc only | +6 parity | +10 parity |
|---|---|---|---|
| −13 dB | 98% | 100% | 100% |
| −15 dB | 90% | **100%** | **100%** |
| −16 dB | 57% | **95%** | **100%** |
| −17 dB | 5% | **62%** | **92%** |
| −18 dB | 0% | 32% | 30% |

Six parity bytes move the usable floor down by roughly 2 dB and cost 0.48 s, taking a full
report from 1.72 s to 2.20 s. At −17 dB that is the difference between one report in
twenty arriving and three in five.

Ten parity bytes buy roughly another 1 dB for a further 0.32 s. Six is the better trade on
a shared channel, where airtime is the scarce resource — but the level is now a parameter,
so a station on a bad link can spend more.

### The layering, deliberately

Reed-Solomon can *miscorrect*: given more errors than it can handle it may land on a
different valid codeword and hand back confident nonsense. That is exactly why the CRC
stays underneath it. Two hundred frames at −18 dB, where a third of frames need repair:
**zero accepted-but-wrong**. Reed-Solomon repairs, the CRC has the final say.

### One thing the frame needed first

The receiver reads the length byte to know how many symbols to collect — so a corrupted
length byte breaks decoding before Reed-Solomon can help. The length is now sent three
times and resolved by majority vote, at a cost of 0.16 s. Protection has to start with the
field that tells you how much there is to protect.

---

## Weekend 6 - reaching further without buying anything

**Goal:** the acoustic range was a couple of metres. Find the free decibels.

### Slowing down is the lever

Range is set by the signal-to-noise ratio at the detector, and the detector's gain comes
from how long it integrates. Doubling the symbol length doubles the window: **+3 dB**.
Sound falls about 6 dB each time the distance doubles, so +6 dB is roughly twice the range.

Three modes, chosen so the existing tones stay exactly on bin centres at every symbol
length (1000, 1200, 1400 and 1600 Hz are whole multiples of 12.5 Hz, the bin spacing at
80 ms):

| mode | symbol | rate | preamble |
|---|---|---|---|
| fast | 20 ms | 100 bps | 100 ms |
| far | 40 ms | 50 bps | 200 ms |
| farthest | 80 ms | 25 bps | 400 ms |

**The receiver is not told which mode was used.** The preamble is found first, then each
mode is tried until one produces a frame that passes Reed-Solomon and the CRC. A station
can therefore switch to a slower mode without anyone reconfiguring the base.

### The first attempt only bought 1 dB, and the reason was the interesting part

Lengthening the symbols alone gave +1 dB and +2 dB, not the predicted +3 and +6. Rather
than accept it, the two failure paths were separated - how often the preamble was found,
against how often the data decoded once it had been:

| SNR | mode | preamble found | decoded when found |
|---|---|---|---|
| -18 dB | fast | 90% | 22% |
| -18 dB | farthest | 78% | 97% |
| -20 dB | fast | 48% | 0% |
| -20 dB | farthest | 45% | **100%** |

The long modes had made the data almost indestructible and turned the fixed 100 ms chirp
into the ceiling. At -20 dB the payload decoded every single time it was heard at all; the
system was failing entirely at the front door.

**The bottleneck had moved, and the fix had to move with it.** A matched filter gains the
same way a symbol detector does, so the preamble now scales with the mode: 100, 200 and
400 ms. With both scaled together:

| SNR | fast | far | farthest |
|---|---|---|---|
| -16 dB | 92% | 100% | 100% |
| -18 dB | 8% | 100% | 100% |
| -20 dB | 0% | 60% | 100% |
| -22 dB | 0% | 0% | **96%** |

| mode | airtime | works down to | gain | range |
|---|---|---|---|---|
| fast | 2.28 s | -16 dB | - | 1.0x |
| far | 4.54 s | -19 dB | +3 dB | 1.4x |
| farthest | 9.06 s | -21 dB | +5 dB | 1.8x |

Measured +3 and +5 dB against a predicted +3 and +6. In a shelter, nobody minds whether
the beep lasts two seconds or nine.

### A false decode, found by accident

While testing mode detection, an 80 ms transmission decoded successfully *as* a 20 ms one.
Reading long tones in short windows repeats each symbol four times, which turned the three
length bytes into `00 55 00` - majority vote gave a length of **zero**, and Reed-Solomon,
with six parity bytes guarding a single data byte, cheerfully corrected the garbage into a
valid empty codeword whose CRC also passed.

This is exactly the miscorrection the CRC was supposed to catch, happening because a
7-byte codeword with 6 parity bytes leaves the decoder far too much freedom. Two fixes:

- a **frame carrying nothing is rejected outright**, since it is never legitimate;
- a **format version byte** now rides inside the protected region, so a false decode must
  also land on the right version. With the CRC that is roughly one in 65,000 rather than
  one in 256.

The version byte pays a second dividend. Audio recorded before a format change now fails
with something a person can act on rather than a puzzle, which matters because every
change to the frame silently invalidates every wav file already recorded - something that
had already caused an hour of confusion once.

### Free decibels still on the table

Tones sit at 1000-1600 Hz, but small phone and laptop speakers usually move far more air
around 2-3 kHz. `experiments/response.py` sweeps 400-3600 Hz through the actual speaker
and microphone, measures what comes back, and recommends the best four tones 200 Hz apart
that stay bin-aligned in every mode. If the answer is more than 1.5 dB better than the
current set it says so; if not it says to leave them alone. Not run yet - it needs the
hardware.

Also free, and not yet measured: turning off the microphone's noise suppression and
automatic gain, which are tuned for speech and fight steady tones; resting the phone on a
hard surface as a soundboard; and cupping something around the speaker to aim it.

---

## Files

Laid out along the seam in the design: the radio half does not know what a shelter is, and
the island half does not know what a tone is.

| where | what it is |
|---|---|
| `soundout/radio/tones.py` | 4-FSK encoder and the Goertzel detector |
| `soundout/radio/preamble.py` | the chirp, the matched filter, both sync methods |
| `soundout/radio/framing.py` | bytes to symbols, triple length, CRC-8, Reed-Solomon wrapping |
| `soundout/radio/reedsolomon.py` | GF(256) arithmetic and the Reed-Solomon codec |
| `soundout/radio/link.py` | transmit and receive a frame |
| `soundout/radio/channel.py` | a simulated channel for testing without hardware |
| `soundout/radio/devices.py` | finding an input and output on the same host API |
| `soundout/radio/wav.py` | wav reading and writing |
| `soundout/island/situation.py` | the 12-byte schema and its bit packing |
| `soundout/island/trust.py` | HMAC tags, Ed25519, key derivation |
| `soundout/island/reports.py` | compose, authenticate, ingest |
| `soundout/island/store.py` | the observation set and the fold |
| `tools/` | the things a human runs |
| `experiments/` | every measurement quoted in this journal |

Reorganising also removed three copies of the same logic: composing a report lived in
`report.py`, authenticating one lived in `receiver.py`, and the simulated channel lived in
`loopback.py` while three experiments imported it from there. All three now sit in the
library, and the tools are thin command lines over it. Every experiment produces
byte-identical results to before the move, which is the only reason to believe the
refactor changed nothing.

## Next

- [x] Preamble + cross-correlation sync, replacing the energy threshold
- [x] Packet framing with a length field and a CRC
- [x] Real hardware: speaker to microphone, decoded exactly
- [x] Long-range modes, worth 5 dB and roughly double the distance
- [ ] Measure the speaker and microphone response, move the tones if it pays
- [ ] Across a room, then over a radio
- [x] The 12-byte situation schema, replacing free text
- [x] Authentication: HMAC tags for reports, Ed25519 for authority broadcasts
- [x] Convergent store and the island picture
- [x] Live receiver and dashboard
- [x] Forward error correction, worth about 2 dB for 0.48 s
- [ ] Over a handheld radio, and across a room at distance
- [ ] The mobility simulator and the comparison chart
