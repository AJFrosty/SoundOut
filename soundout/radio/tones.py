import numpy as np

RATE = 44100
SYMBOL_MS = 20
TONES = [1000, 1200, 1400, 1600]

MODES = {
    "fast": {"symbol_ms": 20, "chirp_ms": 100},
    "far": {"symbol_ms": 40, "chirp_ms": 200},
    "farthest": {"symbol_ms": 80, "chirp_ms": 400},
}


def mode_settings(mode):
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from: {', '.join(MODES)}")
    return MODES[mode]


def bin_spacing(rate=RATE, symbol_ms=SYMBOL_MS):
    return rate / symbol_length(rate, symbol_ms)


def is_aligned(tones, rate=RATE, symbol_ms=SYMBOL_MS):
    spacing = bin_spacing(rate, symbol_ms)
    return all(abs(f / spacing - round(f / spacing)) < 1e-9 for f in tones)


def align(tones, rate=RATE, symbol_ms=SYMBOL_MS):
    spacing = bin_spacing(rate, symbol_ms)
    return [round(round(f / spacing) * spacing) for f in tones]


def rate_bps(symbol_ms=SYMBOL_MS):
    return 2 * 1000 / symbol_ms


def symbol_length(rate=RATE, symbol_ms=SYMBOL_MS):
    return int(rate * symbol_ms / 1000)


def goertzel_power(samples, freq, rate=RATE):
    w = 2.0 * np.pi * freq / rate
    coeff = 2.0 * np.cos(w)

    s1 = 0.0
    s2 = 0.0
    for x in samples:
        s0 = float(x) + coeff * s1 - s2
        s2 = s1
        s1 = s0

    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def goertzel_amplitude(samples, freq, rate=RATE):
    power = goertzel_power(samples, freq, rate)
    return 2.0 * np.sqrt(max(power, 0.0)) / len(samples)


def detect(samples, tones=TONES, rate=RATE):
    amplitudes = [goertzel_amplitude(samples, f, rate) for f in tones]
    order = np.argsort(amplitudes)[::-1]

    best = int(order[0])
    runner_up = amplitudes[int(order[1])]
    margin = amplitudes[best] / runner_up if runner_up > 1e-12 else float("inf")

    return tones[best], amplitudes, margin


def tone(freq, samples, rate=RATE, amplitude=0.5, phase=0.0):
    t = np.arange(samples) / rate
    return amplitude * np.sin(2.0 * np.pi * freq * t + phase)


def encode(symbols, tones=TONES, rate=RATE, symbol_ms=SYMBOL_MS, amplitude=0.5):
    n = symbol_length(rate, symbol_ms)
    return np.concatenate([tone(tones[s], n, rate, amplitude) for s in symbols])


def decode(signal, tones=TONES, rate=RATE, symbol_ms=SYMBOL_MS):
    n = symbol_length(rate, symbol_ms)
    out = []

    for start in range(0, len(signal) - n + 1, n):
        found, _, margin = detect(signal[start:start + n], tones, rate)
        out.append((tones.index(found), margin))

    return out


def bins_are_aligned(tones=TONES, rate=RATE, symbol_ms=SYMBOL_MS):
    n = symbol_length(rate, symbol_ms)
    return {f: n * f / rate for f in tones}
