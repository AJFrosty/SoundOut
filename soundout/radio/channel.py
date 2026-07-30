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
