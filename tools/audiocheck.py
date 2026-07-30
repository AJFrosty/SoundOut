import threading
import time

import numpy as np
import sounddevice as sd

from soundout.radio.tones import RATE, tone

DURATION = 1.5


def level(device, playing):
    captured = {}

    def record():
        captured["data"] = sd.rec(
            int(RATE * DURATION), samplerate=RATE, channels=1, device=device, blocking=True)

    thread = threading.Thread(target=record)
    thread.start()
    time.sleep(0.2)

    if playing:
        sd.play(tone(1200, int(RATE * 1.0), amplitude=0.8), RATE, blocking=True)

    thread.join()
    data = captured["data"].flatten().astype(np.float64)
    return np.sqrt(np.mean(data ** 2)), np.abs(data).max()


if __name__ == "__main__":
    devices = sd.query_devices()
    inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

    print("input devices:")
    for i, name in inputs:
        print(f"  {i}: {name}")

    for i, name in inputs:
        try:
            quiet_rms, quiet_peak = level(i, playing=False)
            loud_rms, loud_peak = level(i, playing=True)
            print(f"\ndevice {i} — {name}")
            print(f"  silent : rms {quiet_rms:.6f}  peak {quiet_peak:.6f}")
            print(f"  playing: rms {loud_rms:.6f}  peak {loud_peak:.6f}")
            print(f"  verdict: {'CAPTURES AUDIO' if loud_rms > max(quiet_rms * 3, 1e-4) else 'silent'}")
        except Exception as error:
            print(f"\ndevice {i} — {name}\n  failed: {error}")
