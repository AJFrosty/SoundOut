<img src="docs/logo.svg" width="72" align="left" alt="">

# SoundOut

**Structured disaster reports carried over sound**, so an island can keep a shared situation
picture when the towers and the power are down. A phone with no signal can still make a
noise, and a handheld radio still carries it.

Not a chat app. Reports are a 12-byte binary schema, authenticated, merged into one picture
that converges no matter what order devices hear each other in.

## Layout

The split is the real seam in the design: **the radio half does not know what a shelter is,
and the island half does not know what a tone is.**

```
soundout/radio/     getting bytes through the air
  tones.py          4-FSK encoder, Goertzel detector
  preamble.py       chirp, matched filter, detection statistics
  framing.py        bytes to symbols, length, CRC-8
  link.py           transmit and receive a frame
  channel.py        a simulated channel, for testing without hardware
  wav.py            read and write wav files

soundout/island/    what the bytes mean
  situation.py      the 12-byte schema and its bit packing
  trust.py          HMAC tags for reports, Ed25519 for authority broadcasts
  reports.py        compose, authenticate, ingest
  store.py          the observation set and the fold that becomes the picture

tools/              things a human runs
  report.py         compose and transmit a situation report
  receiver.py       listen continuously, authenticate, merge
  dashboard.py      the island picture on localhost
  listen.py         record once and decode whatever is heard
  airtest.py        play and record at the same time
  loopback.py       raw symbol burst, kept because it documents the first failure
  audiocheck.py     which input devices actually capture

experiments/        the measurements behind every claim in the journal
  selftest.py       bin alignment, amplitude, rejection, noise, timing
  synctest.py       energy threshold against matched filter
  calibrate.py      where the detection threshold came from
  schematest.py     schema round trip, overflow, forgery, airtime
  storetest.py      order independence, idempotence, tie breaks
  demotest.py       four reports over a noisy channel into one picture

docs/JOURNAL.md     the reasoning, the measurements and the failures
```

Nothing needs installing. Every tool works either way:

```
python -m tools.report --shelter 37 --people 42     # from the repository root
cd tools && python report.py --shelter 37 --people 42   # or from inside the folder
```

## The field device is a web page

`field.html` is the whole reporting end: open it on any phone, from a file or a memory
card, with no internet and no install. Tap the shelter's numbers, hold the phone to a
radio microphone, press transmit.

It reimplements the schema, HMAC-SHA256, CRC-8, Reed-Solomon and the modem in about 300
lines of plain JavaScript, with no libraries and no network requests, so it works from a
`file://` URL on a phone that has never seen a network. On load it checks its own output
against vectors produced by the Python reference and shows a green dot only if the schema,
key derivation, tag, CRC and Reed-Solomon parity all match byte for byte.

That is the point of the project in one file: the person reporting needs a phone and
nothing else — no app store, no licence, no training, no signal.

## Installing

```
pip install -r requirements.txt
```

Three packages: numpy, sounddevice and cryptography. Everything else comes from Python's
standard library, deliberately — a tool meant for the hour after a hurricane should install
cleanly on a laptop with a poor connection.

On Linux, sounddevice needs PortAudio present: `sudo apt install libportaudio2`.

Optionally install the project itself, which adds `soundout-report`, `soundout-receiver`,
`soundout-listen` and `soundout-selfcheck` to your path:

```
pip install -e .
```

Neither is needed for `field.html`. That is plain HTML and JavaScript with no libraries, so
the phone doing the reporting installs nothing at all.

## Try it without hardware

```

python -m experiments.selftest       # the detector, measured against noise
python -m experiments.synctest       # why the preamble replaced loudness
python -m experiments.calibrate      # how the threshold was chosen
python -m experiments.demotest       # four reports become one picture
python -m experiments.storetest      # the merge properties
```

## Send something

```
python -m soundout.radio.link --text "HELLO ANTIGUA" --play
python -m soundout.radio.link --text "TEST" --wav t.wav
python -m soundout.radio.link --decode t.wav

python -m tools.report --shelter 37 --people 42 --capacity 60 \
                       --needs water,insulin --access impassable
```

## The live demo, three terminals

```
python -m tools.dashboard                    # http://localhost:8000
python -m tools.receiver --device 1          # listens, authenticates, merges
python -m tools.report --shelter 12 --people 180 --capacity 180 --needs water,food
```

`python -m tools.audiocheck` first if you are not sure which device is which.

If anything misbehaves, ask the system to check itself:

```
python -m tools.selfcheck
```

It loads every module, pushes a report through memory, a wav file and the receiver's own
path, delivers it through a noisy channel, lists your audio devices, and flags any wav
files left over from an older frame format. Audio recorded before a format change cannot
decode and has to be regenerated — the check names those files.

## Is it worth it?

`docs/comparison.svg` puts SoundOut against what an island actually has. The measure is
**staleness** - how old the information the base is acting on is - because a coordinator
sending water does not ask whether a report arrived, but how old the number is.

```
python -m experiments.comparison
```

| hour | nothing | a runner | cellular | SoundOut | a perfect link |
|---|---|---|---|---|---|
| 6 | 6.0 | 6.0 | 6.0 | **3.1** | 2.5 |
| 24 | 24.0 | 9.2 | 24.0 | **4.4** | 2.8 |
| 60 | 14.7 | 8.7 | **2.8** | 6.2 | 2.7 |

A perfect link settles at 2.9 h rather than zero, because the island keeps changing while
you watch it. That is the floor, and SoundOut runs close to it while the phones are down.
Once they return, cellular wins outright - the claim is not that a $50 radio beats a
working phone network, but that the window where nothing else works is when the reports
matter most.

The honest cost: **9% of shelters have no neighbour in reach and are never heard from at
all**, while a runner is three times staler but eventually reaches everybody. They are
complements rather than competitors.

Time for the base to learn about a new emergency: **0.5 h** by SoundOut, 6.8 h by runner,
42 h waiting for the phones.

## Passing it on

A station can repeat what it heard. That is the difference between this and a walkie-talkie:
a shelter behind a hill reaches the base through a neighbour, and the two ends never have to
be awake at the same moment.

```
python -m tools.relay --radio          # listen, remember, repeat
python -m tools.relay --listen-only    # a plain receiver, for comparison
python -m experiments.relaytest        # what relaying is worth
```

A relay forwards the original bytes including the reporter's tag, so it can choose what to
repeat but never what to say - the base still verifies whoever first wrote the report.
Each station repeats each observation **once**, which is what makes the traffic stop: with
N stations an observation is transmitted at most N times, whatever the island looks like.
When several are waiting they go out worst-first, by casualties, then life-safety needs,
then being cut off.

| minutes | no relay | relaying | what the geography allows |
|---|---|---|---|
| 3.6 | 41% | 59% | 92% |
| 7.1 | 41% | 70% | 92% |
| 28.6 | 41% | 79% | 92% |

Without relaying the curve stops dead and waiting longer does not move it.

## Over a radio

Through the air, sound reaches a few metres and no amount of signal processing changes
that. A radio carries the distance instead: the sound only has to cross the couple of
centimetres from a phone speaker to a radio microphone at one end, and from the radio's
speaker to a laptop microphone at the other.

```
python -m tools.report --shelter 37 --people 42 --radio
python -m experiments.radiohop       # what a radio does to the signal
```

`--radio` puts a **wake-up tone** in front of the transmission. A radio has to be keyed to
transmit, and voice-activated transmit (VOX) keys it on hearing sound - but VOX takes
100-200 ms to open, and the first thing it would otherwise eat is the chirp that the whole
receiver syncs on. The tone is 300 ms at 2600 Hz followed by a 100 ms gap: it exists to be
destroyed, and by the time the chirp arrives the channel is already open.

| VOX eats | without the tone | with it |
|---|---|---|
| 60 ms | 100% | 100% |
| 120 ms | 0% | 100% |
| 450 ms | 0% | 100% |

It costs 0.40 s. In `field.html` it is a checkbox, on by default.

Two practical notes. On amateur bands **encryption is prohibited**, so reports go out in
the clear with an HMAC tag beside them - the tag proves who sent it and that nothing was
altered, and hides nothing. FRS, PMR446 and CB need no licence at all. And radios compand
hard: too loud clips, too quiet never opens VOX, so set the level with the receiver's
meter running.

## Reaching further

Slower modes integrate for longer and so hear a weaker signal. The receiver is not told
which was used - it finds the preamble, then tries each mode until one passes.

```
python -m tools.report --shelter 37 --people 42 --mode farthest
python -m experiments.rangegain      # what each mode buys
python -m experiments.response       # where your speaker is actually loudest
python -m tools.rangetest --distance 2 --note quiet
python -m tools.rangetest --summary  # the curve, once you have a few
```

`rangetest` listens for half a minute, finds every burst in the recording and says what
happened to each one: heard and decoded, or heard but lost, or never heard at all. That
distinction is the whole diagnosis. A healthy PSR with failing frames means the data is
the limit, so slow down. A PSR sliding towards 8 means the preamble is the limit, and no
amount of error correction will help.

| mode | rate | airtime | works down to | range |
|---|---|---|---|---|
| fast | 100 bps | 2.3 s | -16 dB | 1.0x |
| far | 50 bps | 4.5 s | -19 dB | 1.4x |
| farthest | 25 bps | 9.1 s | -21 dB | 1.8x |

## Parameters

| | |
|---|---|
| sample rate | 44100 Hz |
| symbol | 20 ms, 4-FSK at 1000/1200/1400/1600 Hz |
| rate | 50 baud, 2 bits per symbol, 100 bps |
| preamble | 100 ms chirp, 800-2400 Hz |
| frame | chirp, guard, length, payload, CRC-8 |
| report | 12 bytes, plus a 4-byte authentication tag |
| airtime | 1.56 s for a full authenticated report |

## Where it stands

Working and measured: symbol detection to -15 dB SNR, sample-exact synchronisation to
-10 dB, 100% message delivery to -10 dB, zero undetected corruptions in 200 damaged
frames, and a convergent picture across 200 random orderings. Proven on real hardware:
a signed report played through a headset earpiece, captured by that headset's microphone,
and decoded exactly.

Not done yet: forward error correction, a handheld radio hop, and the mobility simulation.
