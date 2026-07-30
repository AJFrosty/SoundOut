import numpy as np

from goertzel import RATE

CHIRP_MS = 100
CHIRP_LOW = 800
CHIRP_HIGH = 2400
GUARD_MS = 20


def chirp(rate=RATE, duration_ms=CHIRP_MS, low=CHIRP_LOW, high=CHIRP_HIGH, amplitude=0.5):
    n = int(rate * duration_ms / 1000)
    t = np.arange(n) / rate
    seconds = duration_ms / 1000.0

    sweep = low * t + (high - low) * t * t / (2 * seconds)
    wave = np.sin(2 * np.pi * sweep)

    taper = int(n * 0.1)
    window = np.ones(n)
    window[:taper] = np.linspace(0, 1, taper)
    window[-taper:] = np.linspace(1, 0, taper)

    return amplitude * wave * window


def guard(rate=RATE, duration_ms=GUARD_MS):
    return np.zeros(int(rate * duration_ms / 1000))


def matched_filter(signal, template):
    n = len(signal) + len(template) - 1
    size = 1 << (n - 1).bit_length()

    spectrum = np.fft.rfft(signal, size)
    reversed_template = np.fft.rfft(template[::-1], size)

    return np.fft.irfft(spectrum * reversed_template, size)[:n]


def normalised_peak(signal, template, peak, chirp_start):
    window = signal[max(chirp_start, 0):chirp_start + len(template)]

    if len(window) < len(template):
        window = np.pad(window, (0, len(template) - len(window)))

    energy = np.linalg.norm(window) * np.linalg.norm(template)
    return abs(float(np.dot(window, template))) / energy if energy > 1e-12 else 0.0


def peak_to_sidelobe(magnitude, peak, guard):
    low = max(peak - guard, 0)
    high = min(peak + guard, len(magnitude))

    sidelobe = np.concatenate([magnitude[:low], magnitude[high:]])
    if len(sidelobe) < 2:
        return float("inf")

    spread = sidelobe.std()
    return (magnitude[peak] - sidelobe.mean()) / spread if spread > 1e-12 else float("inf")


def find_burst(signal, template=None, rate=RATE, guard_ms=GUARD_MS, min_psr=8.0):
    if template is None:
        template = chirp(rate)

    correlation = matched_filter(signal, template)
    magnitude = np.abs(correlation)

    peak = int(np.argmax(magnitude))
    chirp_start = peak - len(template) + 1

    psr = peak_to_sidelobe(magnitude, peak, len(template))
    match = normalised_peak(signal, template, peak, chirp_start)

    data_start = chirp_start + len(template) + int(rate * guard_ms / 1000)

    return {
        "data_start": data_start,
        "chirp_start": chirp_start,
        "psr": psr,
        "match": match,
        "found": psr >= min_psr and chirp_start >= 0,
    }
