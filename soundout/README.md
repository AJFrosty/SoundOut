# soundout — the library

Two layers, deliberately kept apart.

| folder | what it knows about |
|---|---|
| [`radio/`](radio/) | Sound. Bytes in, audio out, audio in, bytes out. Knows nothing about shelters or people. |
| [`island/`](island/) | Meaning. What a shelter can say, who is allowed to say it, what to keep, and what to pass on. |

The split is worth keeping. `radio` can be tested against pure noise with no notion of what
it is carrying, and `island` can be tested with no audio at all — most of
`experiments/storetest.py` and `experiments/schematest.py` never make a sound. When
something breaks it is usually obvious which side of the line it is on.

Nothing in `radio` imports from `island`. The dependency only runs one way.

## The whole path, in one direction

```
  a person at a shelter
        |
        v
  island/situation.py     pack 12 bytes
  island/trust.py         add a 4-byte tag proving who wrote it
        |
        v
  radio/framing.py        length, version, CRC, Reed-Solomon parity
  radio/tones.py          two bits per symbol, one tone each
  radio/preamble.py       a chirp in front so the far end can find the start
        |
        v
     ~ sound ~            a speaker, some air, a radio, some more air, a microphone
        |
        v
  radio/preamble.py       matched filter finds the chirp
  radio/tones.py          Goertzel decides which tone each symbol was
  radio/framing.py        check the CRC, repair damaged bytes
        |
        v
  island/reports.py       check the tag
  island/store.py         keep it; the picture is a fold over everything kept
  island/relay.py         decide whether to pass it on to somebody else
```

## Where to start reading

- **How does the sound work?** `radio/tones.py`, then `radio/preamble.py`.
- **What is actually being said?** `island/situation.py`.
- **How does the base end up with a correct picture?** `island/store.py`.
- **Why is any of it like this?** `docs/JOURNAL.md`.

Each folder has its own README with the file-by-file breakdown and the things to know
before changing anything in it.
