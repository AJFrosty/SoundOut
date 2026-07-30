import numpy as np

from .tones import RATE


def through_simulated_channel(padded, snr_db, rng, out_delay=None):
    delay = rng.integers(int(RATE * 0.05), int(RATE * 0.30))
    if out_delay is not None:
        out_delay.append(int(delay))
    delayed = np.concatenate([np.zeros(delay), padded, np.zeros(int(RATE * 0.2))])

    smoothed = np.convolve(delayed, np.ones(3) / 3.0, mode="same")
    gain = float(rng.uniform(0.2, 0.9))
    faded = smoothed * gain

    signal_power = np.mean(faded[faded != 0] ** 2) if np.any(faded) else 1.0
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    noisy = faded + rng.normal(0.0, np.sqrt(noise_power), len(faded))

    return np.clip(noisy, -0.95, 0.95)


def band_limit(signal, rate=RATE, low=300, high=3000):
    spectrum = np.fft.rfft(signal)
    frequencies = np.fft.rfftfreq(len(signal), 1 / rate)
    spectrum[(frequencies < low) | (frequencies > high)] = 0
    return np.fft.irfft(spectrum, len(signal))


def through_radio(signal, snr_db, rng, vox_clip_ms=180, squelch_ms=60,
                  compression=0.6, hiss=0.004, rate=RATE):
    """A handheld radio's idea of hospitality.

    VOX opens late and eats the beginning. The audio path passes roughly 300-3000 Hz.
    Companding squashes the dynamic range. Opening and closing the squelch adds a burst
    of noise at each end.

    The clip is measured from the moment sound arrives, not from the start of the
    recording — VOX keys on hearing something, so silence beforehand costs nothing.
    """
    loud = np.flatnonzero(np.abs(signal) > 0.02)
    heard_at = int(loud[0]) if len(loud) else 0

    opened = signal.copy()
    opened[heard_at:heard_at + int(rate * vox_clip_ms / 1000)] = 0.0

    shaped = band_limit(opened, rate)

    loudest = np.abs(shaped).max() or 1.0
    companded = np.sign(shaped) * loudest * (np.abs(shaped) / loudest) ** compression

    # a receiver is never digitally silent, and a block of exact zeros has no sidelobes,
    # which sends the peak-to-sidelobe ratio to infinity and invents a preamble
    noise_power = np.mean(companded ** 2) / (10.0 ** (snr_db / 10.0))
    deviation = max(np.sqrt(noise_power), hiss)
    noisy = companded + rng.normal(0.0, deviation, len(companded))

    burst = min(int(rate * squelch_ms / 1000), len(noisy) // 2)
    if burst:
        noisy[:burst] += rng.normal(0.0, 0.3, burst)
        noisy[-burst:] += rng.normal(0.0, 0.3, burst)

    return np.clip(noisy, -0.95, 0.95)
