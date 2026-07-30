import numpy as np

from .tones import RATE

CHIRP_MS = 100
CHIRP_LOW = 800
CHIRP_HIGH = 2400
GUARD_MS = 20

WAKE_MS = 300
WAKE_GAP_MS = 100
WAKE_HZ = 2600


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


def wake(rate=RATE, duration_ms=WAKE_MS, gap_ms=WAKE_GAP_MS, freq=WAKE_HZ, amplitude=0.7):
    """A throwaway tone that keys a radio before anything worth hearing is sent.

    VOX takes a moment to open, and whatever arrives first is chewed. The frequency sits
    above the chirp's 800-2400 Hz sweep so it cannot feed the matched filter, and inside
    the 300-3400 Hz band a voice radio will pass. The gap that follows lets the
    transmitter settle while VOX hang time keeps the channel open.
    """
    samples = int(rate * duration_ms / 1000)
    t = np.arange(samples) / rate

    taper = max(int(samples * 0.05), 1)
    window = np.ones(samples)
    window[:taper] = np.linspace(0, 1, taper)
    window[-taper:] = np.linspace(1, 0, taper)

    tone = amplitude * window * np.sin(2 * np.pi * freq * t)

    return np.concatenate([tone, np.zeros(int(rate * gap_ms / 1000))])


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
    """Find where the chirp starts.

    Only the strongest peak is considered. Trying the next-best few as well was built
    and measured, on the theory that a radio keying up cracks broadband and could
    outrank the chirp; it could not. The matched filter integrates the chirp coherently
    over its whole length, while an impulse only adds up as a square root, so a crack
    four times louder than the signal still lost. The extra machinery was removed.
    """
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


def find_start_by_energy(recorded, block=256, threshold=0.25):
    blocks = len(recorded) // block
    rms = np.array([
        np.sqrt(np.mean(recorded[i * block:(i + 1) * block] ** 2)) for i in range(blocks)
    ])

    if rms.max() < 1e-6:
        raise SystemExit("recorded silence - check the output device and the volume")

    loud = np.flatnonzero(rms > rms.max() * threshold)
    return int(loud[0] * block)
