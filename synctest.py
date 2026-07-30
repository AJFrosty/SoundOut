import numpy as np

from goertzel import RATE
from loopback import find_start, through_simulated_channel
from message import receive, transmit
from preamble import CHIRP_MS, GUARD_MS, chirp, find_burst

RNG = np.random.default_rng(11)
MESSAGE = "SHELTER 37 42PPL NO INSULIN ROAD BLOCKED"


def padded_burst(payload, rng, snr_db):
    signal = transmit(payload)
    lead = np.zeros(int(RATE * 0.4))
    padded = np.concatenate([lead, signal, np.zeros(int(RATE * 0.4))])

    delay = []
    received = through_simulated_channel(padded, snr_db, rng, delay)
    true_start = delay[0] + len(lead)

    return received, true_start


def sync_accuracy(trials=40):
    print("where does each method think the burst starts? (error in samples, 40 trials)")
    print("  SNR dB   energy threshold        matched filter")

    for snr in (20, 10, 5, 0, -5, -10):
        energy_errors = []
        chirp_errors = []

        for _ in range(trials):
            received, true_start = padded_burst(MESSAGE, RNG, snr)

            try:
                energy_errors.append(abs(find_start(received) - true_start))
            except SystemExit:
                energy_errors.append(len(received))

            found = find_burst(received)
            chirp_errors.append(abs(found["chirp_start"] - true_start))

        energy = np.median(energy_errors)
        matched = np.median(chirp_errors)
        print(f"  {snr:6d}   {energy:9.0f} samples      {matched:6.0f} samples")


def message_delivery(trials=40):
    print(f"\nfull message through the channel: \"{MESSAGE}\"")
    print(f"  {len(MESSAGE)} bytes, {len(transmit(MESSAGE)) / RATE:.2f} s of audio")
    print("  SNR dB   delivered   crc caught   no preamble   median margin")

    for snr in (20, 10, 5, 0, -5, -10, -15):
        delivered = 0
        crc_caught = 0
        missing = 0
        margins = []

        for _ in range(trials):
            received, _ = padded_burst(MESSAGE, RNG, snr)
            result = receive(received)

            if result["ok"]:
                if result["text"] == MESSAGE:
                    delivered += 1
                    margins.append(result["median_margin"])
                else:
                    crc_caught += 1
            elif result["error"] == "no preamble found":
                missing += 1
            else:
                crc_caught += 1

        median = f"{np.median(margins):.1f}x" if margins else "-"
        print(f"  {snr:6d}   {delivered / trials:9.0%}   {crc_caught / trials:10.0%}   "
              f"{missing / trials:11.0%}   {median:>13}")


def corruption_is_caught(trials=200):
    print(f"\ncorrupted frames that slipped past the CRC ({trials} trials)")
    signal = transmit(MESSAGE)
    slipped = 0

    for _ in range(trials):
        damaged = signal.copy()
        start = int(RNG.integers(int(RATE * 0.15), len(damaged) - 2000))
        damaged[start:start + 1500] = RNG.normal(0, 0.5, 1500)

        result = receive(damaged)
        if result["ok"] and result["text"] != MESSAGE:
            slipped += 1

    print(f"  {slipped}/{trials} undetected corruptions "
          f"({'good' if slipped <= trials * 0.01 else 'TOO MANY'})")


def overhead():
    payload = len(MESSAGE)
    audio = len(transmit(MESSAGE)) / RATE
    preamble_s = (CHIRP_MS + GUARD_MS) / 1000

    print("\nwhat the airtime is spent on")
    print(f"  preamble + guard : {preamble_s:.2f} s")
    print(f"  length + crc     : {8 * 2 / 100:.2f} s")
    print(f"  payload          : {payload * 8 / 100:.2f} s ({payload} bytes)")
    print(f"  total            : {audio:.2f} s")
    print(f"  useful fraction  : {payload * 8 / 100 / audio:.0%}")


if __name__ == "__main__":
    sync_accuracy()
    message_delivery()
    corruption_is_caught()
    overhead()
