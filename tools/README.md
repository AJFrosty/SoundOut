# tools — the programs you actually run

Everything here is a command. `soundout/` is the library; this is what a person at a
shelter, a relay station or the base sits in front of.

All of them work either way round, so it does not matter where you are:

```bash
python -m tools.receiver          # from the project root
cd tools && python receiver.py    # from inside the folder
```

## The three roles

| file | who runs it | what it does |
|---|---|---|
| `report.py` | a shelter | Compose a situation report and transmit it. The one command a shelter needs. |
| `receiver.py` | the base | Listen continuously, decode, authenticate and store. Shows a level meter and any orders that come past. |
| `relay.py` | anyone in between | Listen, remember, and repeat what others could not get through. Waits for quiet, spreads its repeats, worst reports first. |
| `broadcast.py` | the base | Send a signed order, or a digest of what has already arrived. |
| `dashboard.py` | the base | A web page showing the current picture, served from the store. |

## Setting up and diagnosing

| file | what it is for |
|---|---|
| `selfcheck.py` | **Run this first, and whenever anything is odd.** Checks dependencies, that every module imports, that a report survives every path, that relaying and signing work, that `field.html` agrees with this build, and lists your audio devices. |
| `audiocheck.py` | Is the microphone hearing anything at all? A bare level meter for when nothing else makes sense. |
| `listen.py` | Record for a few seconds and report the levels. Useful for choosing an input device. |
| `loopback.py` | Speaker to microphone on one machine, repeatedly, and count how many decode. The quickest end-to-end confidence check. |
| `airtest.py` | One transmission across the room, played and recorded together, reporting PSR and margin. |
| `rangetest.py` | Stand further away and measure what happens. Finds every burst in a recording and says whether each was heard, decoded or lost, and logs the results so a range curve builds up over several runs. |

## Doing something useful, start to finish

**Check everything works before you rely on it:**

```bash
python -m tools.selfcheck
python -m tools.loopback --count 5
```

**A shelter sends a report:**

```bash
python -m tools.report --shelter 37 --people 42 --capacity 60 \
    --needs water,insulin --casualties 2 --access impassable

python -m tools.report --shelter 37 --people 42 --radio      # through a radio
python -m tools.report --shelter 37 --people 42 --mode farthest   # slower, reaches further
python -m tools.report --shelter 37 --people 42 --wav out.wav --quiet   # build, do not play
```

**The base listens and shows the picture:**

```bash
python -m tools.receiver --db soundout.db
python -m tools.dashboard --db soundout.db        # then open the address it prints
```

**A station in between passes things on:**

```bash
python -m tools.relay --radio
python -m tools.relay --listen-only        # behave as a plain receiver, for comparison
```

**The base answers:**

```bash
python -m tools.broadcast --order "evacuate now" --scope zone --target 3 --within 2
python -m tools.broadcast --order "boil water before drinking"
python -m tools.broadcast --digest --db soundout.db     # tells shelters what arrived
```

**Find out how far it reaches:**

```bash
python -m tools.rangetest --distance 2 --note "quiet room"
python -m tools.rangetest --distance 5 --note "quiet room"
python -m tools.rangetest --summary
```

## When it does not work

Run `python -m tools.selfcheck` first — it catches most of it. Beyond that:

**Nothing is heard at all.** The wrong input device is almost always the cause. `selfcheck`
lists them; pass `--device N`. On Windows, plugging in headphones can silently mute the
device called "Speakers", so the output may be the problem rather than the input.

**"heard a preamble but lost the data."** The transmission arrived but was too damaged to
decode. Move closer, raise `--amplitude`, or use `--mode far`.

**The level meter reads 1.0000 and says CLIPPING.** Too loud. Lower `--amplitude` or move
the microphone back — a clipped signal decodes worse than a quiet one.

**An old wav file will not decode.** It probably predates a frame format change and never
will. `selfcheck` flags these; regenerate them with `tools/report.py --wav`.

**"Illegal combination of I/O devices."** PortAudio will not record and play across two
different host APIs. `soundout/radio/devices.py` finds a matching pair.
