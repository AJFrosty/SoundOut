import numpy as np

from .framing import (
    LENGTH_COPIES,
    PARITY_BYTES,
    build_frame,
    bytes_to_symbols,
    frame_byte_count,
    parse_frame,
    symbols_to_bytes,
)
from .preamble import chirp, find_burst, guard
from .tones import RATE, TONES, detect, encode, symbol_length

LENGTH_SYMBOLS = 4 * LENGTH_COPIES


def transmit(payload, rate=RATE, amplitude=0.5, parity_bytes=PARITY_BYTES):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    frame = build_frame(payload, parity_bytes)
    symbols = bytes_to_symbols(frame)

    return np.concatenate([
        chirp(rate, amplitude=amplitude),
        guard(rate),
        encode(symbols, amplitude=amplitude),
    ])


def read_symbols(signal, start, count, rate=RATE):
    n = symbol_length(rate)
    symbols = []
    margins = []

    for i in range(count):
        window = signal[start + i * n:start + (i + 1) * n]
        if len(window) < n:
            break
        found, _, margin = detect(window, TONES, rate)
        symbols.append(TONES.index(found))
        margins.append(margin)

    return symbols, margins


def receive(signal, rate=RATE, min_psr=8.0, parity_bytes=PARITY_BYTES):
    burst = find_burst(signal, rate=rate, min_psr=min_psr)

    if not burst["found"]:
        return {"ok": False, "error": "no preamble found", "burst": burst}

    header, _ = read_symbols(signal, burst["data_start"], LENGTH_SYMBOLS, rate)
    if len(header) < LENGTH_SYMBOLS:
        return {"ok": False, "error": "signal ended before the length byte", "burst": burst}

    from .framing import majority_length

    length, error = majority_length(list(symbols_to_bytes(header)))
    if error:
        return {"ok": False, "error": error, "burst": burst}

    total = 4 * frame_byte_count(length, parity_bytes)

    symbols, margins = read_symbols(signal, burst["data_start"], total, rate)
    if len(symbols) < total:
        return {"ok": False, "error": "signal ended mid-frame", "burst": burst,
                "length": length}

    payload, error, corrected = parse_frame(symbols_to_bytes(symbols), parity_bytes)

    if error:
        return {"ok": False, "error": error, "burst": burst, "length": length,
                "median_margin": float(np.median(margins))}

    return {
        "ok": True,
        "payload": payload,
        "text": payload.decode("utf-8", errors="replace"),
        "burst": burst,
        "corrected": corrected,
        "median_margin": float(np.median(margins)),
    }


def duration_seconds(payload_length, rate=RATE):
    from .preamble import CHIRP_MS, GUARD_MS

    symbols = 4 * (1 + payload_length + 1)
    return (CHIRP_MS + GUARD_MS) / 1000 + symbols * symbol_length(rate) / rate


def _send(text, wav_path, play, amplitude):
    signal = transmit(text, amplitude=amplitude)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"message : \"{text}\"")
    print(f"bytes   : {len(text.encode('utf-8'))}")
    print(f"airtime : {len(signal) / RATE:.2f} s")

    if wav_path:
        from .wav import write_wav
        write_wav(wav_path, padded)
        print(f"wrote   : {wav_path}")

    if play:
        import sounddevice as sd
        print("playing — chirp first, then the data")
        sd.play(padded, RATE, blocking=True)
        print("done")


def _decode(wav_path):
    from .wav import read_wav

    signal, rate = read_wav(wav_path)
    result = receive(signal, rate=rate)

    print(f"file      : {wav_path} ({len(signal) / rate:.2f} s)")
    print(f"preamble  : {'found' if result['burst']['found'] else 'NOT FOUND'} "
          f"(PSR {result['burst']['psr']:.1f}, match {result['burst']['match']:.3f})")

    if result["ok"]:
        print(f"decoded   : \"{result['text']}\"")
        repaired = result.get("corrected", 0)
        print(f"repaired  : {repaired} damaged byte{'' if repaired == 1 else 's'}")
        print(f"margin    : {result['median_margin']:.1f}x")
    else:
        print(f"failed    : {result['error']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="SHELTER 37 NO INSULIN")
    parser.add_argument("--wav", type=str, default=None)
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--amplitude", type=float, default=0.4)
    parser.add_argument("--decode", type=str, default=None,
                        help="decode a wav file instead of sending")
    args = parser.parse_args()

    if args.decode:
        _decode(args.decode)
    else:
        _send(args.text, args.wav, args.play, args.amplitude)
