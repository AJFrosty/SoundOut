import numpy as np

from goertzel import (
    RATE,
    SYMBOL_MS,
    TONES,
    bins_are_aligned,
    detect,
    goertzel_amplitude,
    symbol_length,
    tone,
)

RNG = np.random.default_rng(7)
N = symbol_length()


def noisy(signal, snr_db):
    signal_power = np.mean(signal ** 2)
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    return signal + RNG.normal(0.0, np.sqrt(noise_power), len(signal))


def bin_alignment():
    print("bin alignment (must be whole numbers, else the tone leaks across bins)")
    for freq, k in bins_are_aligned().items():
        flag = "ok" if abs(k - round(k)) < 1e-9 else "LEAKS"
        print(f"  {freq:5d} Hz -> bin {k:7.3f}  {flag}")
    print(f"  bin spacing = {RATE / N:.1f} Hz, symbol = {SYMBOL_MS} ms, {N} samples")


def amplitude_accuracy():
    print("\namplitude recovery on a clean tone")
    for amp in (1.0, 0.5, 0.1, 0.01):
        measured = goertzel_amplitude(tone(1200, N, amplitude=amp), 1200)
        print(f"  sent {amp:5.2f} -> measured {measured:6.3f}")


def rejection():
    print("\nrejection: 1200 Hz sent, what every detector reports")
    for freq, amp in zip(TONES, [goertzel_amplitude(tone(1200, N), f) for f in TONES]):
        print(f"  {freq:5d} Hz detector -> {amp:8.5f}")


def noise_sweep(trials=200):
    print(f"\nsymbol accuracy vs noise ({trials} trials per level)")
    print("  SNR dB   accuracy   median margin")

    for snr in (10, 0, -10, -15, -20, -23, -26, -30):
        correct = 0
        margins = []

        for _ in range(trials):
            sent = int(RNG.integers(0, len(TONES)))
            phase = float(RNG.uniform(0, 2 * np.pi))
            signal = noisy(tone(TONES[sent], N, phase=phase), snr)

            found, _, margin = detect(signal)
            margins.append(margin)
            if found == TONES[sent]:
                correct += 1

        print(f"  {snr:6d}   {correct / trials:8.1%}   {np.median(margins):13.2f}")


def timing_offset(trials=100, snr=10):
    print(f"\naccuracy when the window starts late (SNR {snr} dB, {trials} trials)")
    print("  offset ms   accuracy")

    for offset_ms in (0, 1, 2, 5, 10):
        shift = int(RATE * offset_ms / 1000)
        correct = 0

        for _ in range(trials):
            sent = int(RNG.integers(0, len(TONES)))
            neighbour = int(RNG.integers(0, len(TONES)))
            stream = np.concatenate([tone(TONES[sent], N), tone(TONES[neighbour], N)])
            window = noisy(stream[shift:shift + N], snr)

            if detect(window)[0] == TONES[sent]:
                correct += 1

        print(f"  {offset_ms:9d}   {correct / trials:8.1%}")


if __name__ == "__main__":
    bin_alignment()
    amplitude_accuracy()
    rejection()
    noise_sweep()
    timing_offset()
