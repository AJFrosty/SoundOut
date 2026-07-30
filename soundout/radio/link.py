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
from .preamble import chirp, find_burst, guard, wake
from .tones import (
    MODES,
    RATE,
    SYMBOL_MS,
    TONES,
    detect,
    encode,
    mode_settings,
    symbol_length,
)

LENGTH_SYMBOLS = 4 * LENGTH_COPIES


def transmit(payload, rate=RATE, amplitude=0.5, parity_bytes=PARITY_BYTES,
             mode="fast", tones=TONES, radio=False):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    settings = mode_settings(mode)
    frame = build_frame(payload, parity_bytes)
    symbols = bytes_to_symbols(frame)

    parts = [wake(rate, amplitude=amplitude)] if radio else []

    return np.concatenate(parts + [
        chirp(rate, settings["chirp_ms"], amplitude=amplitude),
        guard(rate),
        encode(symbols, tones, rate, settings["symbol_ms"], amplitude),
    ])


def read_symbols(signal, start, count, rate=RATE, symbol_ms=SYMBOL_MS, tones=TONES):
    n = symbol_length(rate, symbol_ms)
    symbols = []
    margins = []

    for i in range(count):
        window = signal[start + i * n:start + (i + 1) * n]
        if len(window) < n:
            break
        found, _, margin = detect(window, tones, rate)
        symbols.append(tones.index(found))
        margins.append(margin)

    return symbols, margins


def decode_at(signal, burst, rate, parity_bytes, symbol_ms, tones):
    header, _ = read_symbols(signal, burst["data_start"], LENGTH_SYMBOLS,
                             rate, symbol_ms, tones)
    if len(header) < LENGTH_SYMBOLS:
        return {"ok": False, "error": "signal ended before the length byte"}

    from .framing import majority_length

    length, error = majority_length(list(symbols_to_bytes(header)))
    if error:
        return {"ok": False, "error": error}

    total = 4 * frame_byte_count(length, parity_bytes)
    symbols, margins = read_symbols(signal, burst["data_start"], total,
                                    rate, symbol_ms, tones)
    if len(symbols) < total:
        return {"ok": False, "error": "signal ended mid-frame", "length": length}

    payload, error, corrected = parse_frame(symbols_to_bytes(symbols), parity_bytes)

    if error:
        return {"ok": False, "error": error, "length": length,
                "median_margin": float(np.median(margins))}

    return {
        "ok": True,
        "payload": payload,
        "text": payload.decode("utf-8", errors="replace"),
        "corrected": corrected,
        "median_margin": float(np.median(margins)),
    }


def receive(signal, rate=RATE, min_psr=8.0, parity_bytes=PARITY_BYTES,
            mode=None, tones=TONES):
    attempts = [(mode, mode_settings(mode))] if mode else list(MODES.items())
    best = None

    for name, settings in attempts:
        template = chirp(rate, settings["chirp_ms"])
        burst = find_burst(signal, template=template, rate=rate, min_psr=min_psr)

        if not burst["found"]:
            if best is None:
                best = {"ok": False, "error": "no preamble found",
                        "burst": burst, "mode": name}
            continue

        outcome = decode_at(signal, burst, rate, parity_bytes,
                            settings["symbol_ms"], tones)
        outcome["burst"] = burst
        outcome["mode"] = name
        outcome["symbol_ms"] = settings["symbol_ms"]

        if outcome["ok"]:
            return outcome

        if best is None or not best["burst"]["found"]:
            best = outcome

    return best


def duration_seconds(payload_length, rate=RATE, mode="fast"):
    from .preamble import GUARD_MS

    settings = mode_settings(mode)
    symbols = 4 * frame_byte_count(payload_length)

    return ((settings["chirp_ms"] + GUARD_MS) / 1000
            + symbols * symbol_length(rate, settings["symbol_ms"]) / rate)


def _send(text, wav_path, play, amplitude, mode="fast", radio=False):
    signal = transmit(text, amplitude=amplitude, mode=mode, radio=radio)
    padded = np.concatenate([np.zeros(int(RATE * 0.3)), signal, np.zeros(int(RATE * 0.3))])

    print(f"message : \"{text}\"")
    print(f"bytes   : {len(text.encode('utf-8'))}")
    print(f"mode    : {mode}")
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
        payload = result["payload"]
        # a situation report is packed binary, not text: printing it as characters puts
        # replacement marks through a console that cannot encode them
        readable = all(32 <= byte < 127 for byte in payload)

        print(f"mode      : {result['mode']} ({result['symbol_ms']} ms symbols)")
        print(f"decoded   : \"{result['text']}\"" if readable
              else f"decoded   : {len(payload)} bytes ({payload.hex()})")
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
    parser.add_argument("--mode", type=str, default="fast", choices=list(MODES),
                        help="slower modes reach further")
    parser.add_argument("--radio", action="store_true",
                        help="lead with a tone that keys a VOX radio")
    parser.add_argument("--decode", type=str, default=None,
                        help="decode a wav file instead of sending")
    args = parser.parse_args()

    from ..island import validate
    from .framing import MAX_PAYLOAD

    if args.decode:
        import os
        if not os.path.exists(args.decode):
            raise SystemExit(f"error: no such file: {args.decode}")
        _decode(args.decode)
    else:
        try:
            validate.text_payload(args.text, MAX_PAYLOAD)
            amplitude = validate.fraction(args.amplitude, "amplitude", 0.05, 1.0)
        except validate.Invalid as error:
            raise SystemExit(f"error: {error}")
        _send(args.text, args.wav, args.play, amplitude, args.mode, args.radio)
