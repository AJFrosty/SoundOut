# Connecting the radio

Follow this with the hardware in front of you. Every step has a way to tell whether it
worked, so when something fails you know which step to go back to rather than starting
again from the beginning.

The most important thing to understand before you start: **the sound only ever has to
cross about two centimetres.** Phone speaker to radio microphone at one end, radio speaker
to laptop microphone at the other. The radio carries the distance. Nothing in the software
is trying to make sound travel across the island — through open air the range is a few
metres and no amount of signal processing changes that.

```
  phone                  radio  ~~~~~~~~~ radio                laptop
  speaker  --2 cm-->  microphone            speaker --2 cm--> microphone
                              the actual distance
```

---

## Step 0 — What to buy

**Two handheld radios.** Any pair that can talk to each other. Roughly US$25–50 each for
the cheap Chinese handhelds; a pair of licence-free consumer radios is fine too and avoids
the licensing question entirely.

| band | licence | notes |
|---|---|---|
| **FRS / PMR446 / CB** | none needed | Simplest for a demonstration. Lower power, shorter range. |
| **Amateur (VHF/UHF)** | operator licence | Much better range, and repeaters. **Encryption is prohibited** — which SoundOut already respects, see below. |

**Cables are optional and you should not buy them first.** Acoustic coupling — holding the
phone next to the radio — works, costs nothing, and removes a whole class of problems.
Read step 7 before spending money on cables.

**What you do not need:** any kind of computer interface, sound card, or TNC. The laptop's
own microphone and speaker are the interface.

### On encryption, if you use amateur bands

Transmitting encrypted data on amateur bands is prohibited in essentially every country.
SoundOut is already built for this: a report travels **in the clear** with an HMAC tag
beside it. The tag proves who wrote it and that nobody altered it on the way. It hides
nothing, deliberately. You are transmitting a signed message, not a secret one, and that is
legal.

---

## Step 1 — Before the radios arrive

Do this now; it removes variables later.

```bash
python -m tools.selfcheck
```

Everything must pass. Then confirm sound gets from your speaker to your microphone at all —
`airtest` plays and records at the same time and tells you what came back:

```bash
python -m tools.airtest --text "DESK TEST"
```

If that decodes across your desk, the software is fine and anything that goes wrong later
is the radio path. Note the PSR and match it reports; those are your known-good numbers to
compare the radio against.

**Turn off the microphone's "enhancements".** Windows applies noise suppression, echo
cancellation and automatic gain control by default. All three are tuned for speech and all
three actively fight steady tones — AGC in particular will chase your signal up and down
mid-frame.

> Settings → System → Sound → your input device → Device properties → Additional device
> properties → **Enhancements** tab → tick "Disable all enhancements". Also check the
> **Advanced** tab and untick "Allow applications to take exclusive control".

Re-run `airtest` afterwards. It should be the same or better; if it got worse, put a
setting back.

---

## Step 2 — Prove the radios work as radios

Before any data, before any cables. Two radios, both switched on.

1. Set **both** to the same channel.
2. Set **both** to the same bandwidth — narrow (12.5 kHz) or wide (25 kHz), it does not
   matter which, but a mismatch makes everything quiet and distorted for no obvious reason.
3. Set **both** to the same CTCSS/DCS tone, or turn tones off on both.
4. Walk into another room, press the transmit key, and talk.

If you cannot hear your own voice clearly, stop here. No amount of software will fix a
radio link that cannot carry speech.

### Turn these off while you are in the menus

| setting | why |
|---|---|
| **Roger beep** / end-of-transmission tone | It appends a beep to every transmission, which is noise the receiver has to sit through. |
| **Voice prompts** / key beeps | The radio will announce menu changes over your data. |
| **Battery save** / power save | **This one matters.** In power save the receiver sleeps in short cycles and wakes when it detects a carrier — which chews the start of every received transmission, exactly like VOX does at the other end. It will look like a mysterious intermittent failure. |
| **Auto power off** | It will switch off mid-test. |

---

## Step 3 — Set up the receiving end first

Receive is easier to verify than transmit, so build it first and you will have a working
instrument to test the other half with.

1. Put the **receiving radio's speaker** about 2 cm from the laptop's microphone.
2. Turn the radio's volume to roughly a third.
3. **Open the squelch** (often called "monitor", or set squelch level to 0). Closed squelch
   mutes weak signals entirely — including ones SoundOut could still decode. You will hear
   hiss. That is correct and the receiver copes with it.

Now start the level meter:

```bash
python -m tools.receiver --verbose
```

It prints a level reading every three seconds. Have someone key the other radio and speak,
or just listen to the open-squelch hiss.

| what you see | what it means |
|---|---|
| `[level 0.0000] silent — is the right device selected?` | Wrong input device. Run `python -m tools.audiocheck` to find which one actually captures, then pass `--device N`. |
| `[level 0.9990] ####  CLIPPING — turn the volume down` | Too loud. Turn the radio's volume down. **A clipped signal decodes worse than a quiet one.** |
| `[level 0.15]` to `[level 0.60]` with a bar | This is what you want. |

Do not move on until an idle radio gives you a small but non-zero level and a keyed radio
pushes the bar up without clipping.

---

## Step 4 — Set up the transmitting end

1. Put the **phone or laptop speaker** about 2 cm from the **transmitting radio's
   microphone**. Find where the microphone hole actually is — on most handhelds it is a
   pinhole near the bottom of the front face, not on the top.
2. Set the phone's volume to about three quarters.

Hold the radio's transmit key down by hand for this first test — VOX comes later, one
variable at a time.

With the receiver from step 3 still running on the laptop:

```bash
python -m tools.report --shelter 37 --people 42 --needs water
```

Press and hold the transmit key on the sending radio, run the command, and keep holding
until the sound finishes. The receiver should print something like:

```
[14:22:05] OK Shelter 37: 42 of 60 places used, needs water, access open
```

**If that worked, the radio link carries data.** Everything after this is convenience.

---

## Step 5 — Get the levels right

This is where most of the difficulty lives, and it is worth ten minutes.

A radio's audio path compresses hard. Too quiet and it never keys or gets buried in hiss;
too loud and it distorts, which destroys the tones far more effectively than noise does.

Work one end at a time:

**Sending end.** Start at about three quarters volume on the phone. Send a report. If it
decodes, drop the volume until it stops decoding, then go back up two steps. If it never
decodes, raise the volume — but if you reach maximum and it is still failing, the problem
is spacing, not volume: move the speaker closer and aim it at the microphone hole.

**Receiving end.** Watch the receiver's level meter while a transmission comes in. Aim for
a bar that moves clearly but never reads `CLIPPING`. If you cannot get both — quiet enough
not to clip, loud enough to decode — the radio's volume control is too coarse; move the
laptop microphone slightly further away instead.

Confirm with a run of ten:

```bash
python -m tools.rangetest --distance 0 --seconds 120 --note "radio, hand keyed"
```

Send repeatedly during those two minutes. It will tell you how many bursts it heard, how
many decoded, and the median PSR. **A median PSR above 15 with everything decoding means
the link is healthy.** PSR sliding towards 8 means you are near the edge.

---

## Step 6 — Turn on VOX

Now the radio can key itself, which is what makes an unattended relay station possible.

1. In the transmitting radio's menu, set **VOX** to a middle sensitivity — on a 1–10 scale
   start at 3 or 4.
2. Set **VOX delay** (sometimes "VOX hang") to about 2 seconds if it is adjustable.

Then send with the wake-up tone:

```bash
python -m tools.report --shelter 37 --people 42 --needs water --radio
```

The `--radio` flag puts 300 ms of tone at 2600 Hz in front of the transmission, followed by
a 100 ms gap. That tone exists **to be destroyed** — VOX takes 100–200 ms to open and eats
whatever it hears first, and without the wake tone that would be the chirp the whole
receiver syncs on. Measured: without it, 120 ms of VOX delay takes delivery from 100% to 0%.
With it, 450 ms is survivable. It costs 0.40 seconds.

**Always use `--radio` when transmitting through a VOX-keyed radio.** In `field.html` it is
a checkbox, on by default.

| symptom | fix |
|---|---|
| The radio never keys | VOX sensitivity too low, or the speaker is too far from the microphone. Raise sensitivity one step at a time. |
| The radio keys on room noise and stays keyed | VOX sensitivity too high. Lower it. |
| It keys, but nothing ever decodes | You forgot `--radio`, or VOX delay is longer than 400 ms. |
| It cuts off before the end | VOX hang time too short. Raise it, or hand-key for long `--mode farthest` transmissions. |

---

## Step 7 — Cables, only if you want them

Acoustic coupling works and is what everything above assumes. A cable is tidier and immune
to room noise, but it introduces a real hazard:

**A laptop headphone output is line level and a radio microphone input expects millivolts.**
Connecting them directly overdrives the input badly. You will get a strong signal that
decodes worse than the acoustic path did, which is a confusing failure.

If you do go the cable route:

- You need an audio cable for your specific radio — for the common Chinese handhelds this
  is a 2-pin Kenwood-style plug, 3.5 mm for speaker and 2.5 mm for microphone. These are
  sold as APRS or programming-and-audio cables, roughly US$10–20.
- Put **attenuation** between the laptop output and the radio's microphone input. A simple
  resistive divider giving roughly 20–40 dB of attenuation is the usual approach.
- Start with the laptop's output volume very low and bring it up.
- Test with `rangetest` exactly as in step 5 and **compare against your acoustic numbers**.
  If the cable is not better, the coupling is wrong — go back to acoustic rather than
  fighting it.

Do the acoustic path first regardless. It gives you a known-good baseline to judge the
cable against.

---

## Step 8 — A relay station

Once two radios work, a third station in between can pass on what neither end can reach:

```bash
python -m tools.relay --radio
```

It listens, keeps what it hears, waits for the air to be quiet, waits a further random
moment so that stations which heard the same report do not all answer at once, and repeats
the worst report first. Each station repeats each observation **once**, which is what makes
the traffic stop rather than echoing forever.

Note the receiving radio for a relay should have **squelch open** as in step 3, and the
transmitting radio needs **VOX on** as in step 6.

---

## Step 9 — Find the actual range

```bash
python -m tools.rangetest --distance 200 --seconds 120 --note "radio, town"
python -m tools.rangetest --distance 800 --seconds 120 --note "radio, town"
python -m tools.rangetest --summary
```

Distances are just labels for the log, so use whatever unit you like as long as you are
consistent. The summary builds a curve as you add runs.

Reading it:

- **Nothing heard at all** — the preamble never rose above the noise. Out of range, or the
  radios are not on the same channel.
- **Heard but not decoded, PSR healthy** — the link is there but the data is marginal. Try
  `--mode far` or `--mode farthest` on the transmitter. The receiver works out which mode
  was used by itself; nothing needs reconfiguring at the base.
- **PSR sliding towards 8** — the preamble is the limit, and error correction cannot help.
  That is the real edge of range.

---

## Quick reference

```bash
# base, listening
python -m tools.receiver --db soundout.db --verbose
python -m tools.dashboard --db soundout.db

# a shelter, through a VOX radio
python -m tools.report --shelter 37 --people 42 --needs water,insulin --radio

# further, if it is not getting through
python -m tools.report --shelter 37 --people 42 --radio --mode farthest

# a station in between
python -m tools.relay --radio

# the base answering
python -m tools.broadcast --order "evacuate now" --scope zone --target 3 --radio
python -m tools.broadcast --digest --db soundout.db --radio

# when something is wrong
python -m tools.selfcheck
python -m tools.audiocheck
python -m tools.airtest --text "DESK TEST"
```

## The five things that will actually go wrong

1. **Wrong input device.** `audiocheck` tells you which one hears anything.
2. **Clipping.** The meter says so explicitly. Quieter is better than louder.
3. **Battery save on the receiving radio**, chewing the start of transmissions.
4. **`--radio` forgotten** on a VOX-keyed transmission, so VOX eats the chirp.
5. **Squelch closed** on the receiving radio, muting signals that would have decoded.
