# SoundOut

Structured disaster reports carried over sound, so an island can keep a shared situation
picture when the towers and the power are down. A phone with no signal can still make a
noise, and a handheld radio still carries it.

Not a chat app. Reports are a compact binary schema, merged into one picture that
converges no matter what order devices hear each other in.

## Status

Weekend 1 of the build: 4-FSK modulation and Goertzel detection working and measured.
Reliable to about −15 dB SNR in simulation. Synchronisation is the current weak point and
the next piece of work — see `JOURNAL.md`.

## Running it

```
pip install numpy sounddevice

python selftest.py                      # no hardware needed
python loopback.py --simulate 15        # 40 symbols through a simulated channel
python loopback.py --simulate 5 --oracle-sync
python audiocheck.py                    # which inputs actually capture
python loopback.py                      # the real thing, once an input works
```

## Parameters

| | |
|---|---|
| sample rate | 44100 Hz |
| symbol | 20 ms (882 samples) |
| tones | 1000, 1200, 1400, 1600 Hz |
| rate | 50 baud, 2 bits/symbol, 100 bps |

Every tone is a whole number of bins at this window length, so nothing leaks between them.
The reasoning behind each choice is in `JOURNAL.md`.
