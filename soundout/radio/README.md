# soundout/radio — turning bytes into sound and back

This is the modem. It knows nothing about shelters, reports or people: give it bytes and it
produces audio, give it audio and it gives back the bytes. Everything above it in
`soundout/island` treats this layer as a pipe that occasionally loses things.

The order below is the order a transmission actually happens in.

| file | what it is for |
|---|---|
| `tones.py` | The four tones, the symbol timing, and the Goertzel detector that decides which tone is present. Also the `MODES` table — fast, far, farthest. |
| `preamble.py` | The chirp that marks the start of a transmission, the matched filter that finds it, and the wake-up tone that keeps a radio's VOX from eating it. |
| `framing.py` | Wraps a payload in a length, a version, a CRC and Reed–Solomon parity, and unwraps it again. |
| `reedsolomon.py` | Error correction over GF(256), written out by hand: Berlekamp–Massey, Chien search, Forney. Repairs damaged bytes instead of discarding the frame. |
| `link.py` | Ties it together. `transmit()` makes audio, `receive()` finds the preamble and decodes. Also runnable directly to send or decode a text message. |
| `channel.py` | Simulated channels for testing without hardware: added noise, and a handheld radio complete with VOX clipping, a narrow passband, companding and squelch cracks. |
| `wav.py` | Reading and writing wav files, so a transmission can be inspected later or replayed. |
| `devices.py` | Finding an input and an output that share a host API. PortAudio refuses to record and play across different ones. |

## The shape of a transmission

```
[ wake-up tone ] [ chirp ] [ guard ] [ symbols carrying the frame ]
   only --radio    sync      20 ms      two bits per symbol
```

And the frame inside those symbols:

```
[ length x3 ] [ version ] [ payload ] [ CRC ] [ RS parity ]
   majority       1 byte    n bytes    1 byte   6 bytes
```

## Using it directly

```bash
# send a text message and hear it
python -m soundout.radio.link --text "SHELTER 37 NO INSULIN" --play

# write it to a file instead, then read it back
python -m soundout.radio.link --text "HELLO" --wav hello.wav
python -m soundout.radio.link --decode hello.wav

# a slower mode reaches further, and the receiver works out which was used
python -m soundout.radio.link --text "HELLO" --mode farthest --wav slow.wav
python -m soundout.radio.link --decode slow.wav
```

From Python:

```python
from soundout.radio.link import transmit, receive

audio = transmit(b"anything up to 200 bytes", mode="far", radio=True)
result = receive(audio)
result["ok"], result["payload"], result["mode"]
```

## Things worth knowing before changing anything here

**The tones are on bin centres.** 1000, 1200, 1400 and 1600 Hz are all whole multiples of
the bin spacing at every symbol length, so a tone that is present lands entirely in its own
bin and the other three read as good as zero. Move a tone off a bin centre and the detector
gets quietly worse in a way that is hard to see.

**PSR 8.0 is calibrated, not chosen.** The preamble threshold was measured: pure noise
worst-cases at about 7.0, a real burst at −15 dB worst-cases at 11.0. Change how the noise
floor is computed and the threshold has to be re-measured — `experiments/calibrate.py`
does that.

**Changing the frame format invalidates every wav file ever recorded.** That is what the
version byte is for, and why `tools/selfcheck.py` looks for stale wavs and checks that
`field.html` still agrees with this build.
