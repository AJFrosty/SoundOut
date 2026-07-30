import argparse
import wave

import numpy as np
import sounddevice as sd

from goertzel import RATE, TONES, decode, encode, symbol_length

LEAD_IN_S = 0.4


def write_wav(path, signal, rate=RATE):
    samples = np.clip(signal, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)

    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def read_wav(path):
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
    return pcm, rate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=20)
    parser.add_argument("--amplitude", type=float, default=0.4)
    parser.add_argument("--wav", type=str, default=None)
    parser.add_argument("--verify", action="store_true",
                        help="read the wav back and decode it, proving the file is valid")
    parser.add_argument("--silent", action="store_true", help="write the wav, play nothing")
    args = parser.parse_args()

    rng = np.random.default_rng()
    sent = [int(s) for s in rng.integers(0, len(TONES), args.symbols)]
    signal = encode(sent, amplitude=args.amplitude)
    padded = np.concatenate([np.zeros(int(RATE * LEAD_IN_S)), signal])

    seconds = len(signal) / RATE
    print(f"symbols : {''.join(str(s) for s in sent)}")
    print(f"tones   : {' '.join(str(TONES[s]) for s in sent[:8])}{' ...' if len(sent) > 8 else ''}")
    print(f"duration: {seconds:.1f} s of audio for {args.symbols} symbols "
          f"({args.symbols * 2} bits)")

    if args.wav:
        write_wav(args.wav, padded)
        print(f"wrote   : {args.wav}")

        if args.verify:
            loaded, rate = read_wav(args.wav)
            start = int(rate * LEAD_IN_S)
            n = symbol_length()
            got = [s for s, _ in decode(loaded[start:start + n * args.symbols])]
            errors = sum(1 for a, b in zip(sent, got) if a != b)
            print(f"decoded : {''.join(str(s) for s in got)}")
            print(f"errors  : {errors}/{args.symbols}")

    if not args.silent:
        print("\nplaying — you should hear a warbling chirp")
        sd.play(padded, RATE, blocking=True)
        print("done")


if __name__ == "__main__":
    main()
