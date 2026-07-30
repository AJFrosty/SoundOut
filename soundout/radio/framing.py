from . import reedsolomon

CRC_POLYNOMIAL = 0x07
MAX_PAYLOAD = 200
PARITY_BYTES = 6
LENGTH_COPIES = 3


def bytes_to_symbols(data):
    symbols = []
    for byte in data:
        symbols.append((byte >> 6) & 0b11)
        symbols.append((byte >> 4) & 0b11)
        symbols.append((byte >> 2) & 0b11)
        symbols.append(byte & 0b11)
    return symbols


def symbols_to_bytes(symbols):
    usable = len(symbols) - (len(symbols) % 4)
    data = bytearray()

    for i in range(0, usable, 4):
        a, b, c, d = symbols[i:i + 4]
        data.append((a << 6) | (b << 4) | (c << 2) | d)

    return bytes(data)


def crc8(data):
    remainder = 0
    for byte in data:
        remainder ^= byte
        for _ in range(8):
            if remainder & 0x80:
                remainder = ((remainder << 1) ^ CRC_POLYNOMIAL) & 0xFF
            else:
                remainder = (remainder << 1) & 0xFF
    return remainder


def build_frame(payload, parity_bytes=PARITY_BYTES):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload is {len(payload)} bytes, limit is {MAX_PAYLOAD}")

    protected = bytes(payload) + bytes([crc8(payload)])
    codeword = reedsolomon.encode(protected, parity_bytes)

    return bytes([len(payload)]) * LENGTH_COPIES + codeword


def majority_length(copies):
    for candidate in copies:
        if sum(1 for other in copies if other == candidate) >= 2:
            return candidate, None
    return None, "the three length bytes all disagree"


def parse_frame(data, parity_bytes=PARITY_BYTES):
    if len(data) < LENGTH_COPIES + 2:
        return None, "frame too short", 0

    length, error = majority_length(list(data[:LENGTH_COPIES]))
    if error:
        return None, error, 0

    expected = LENGTH_COPIES + length + 1 + parity_bytes
    if len(data) < expected:
        return None, f"truncated: need {expected} bytes, have {len(data)}", 0

    codeword = data[LENGTH_COPIES:expected]
    repaired, corrected, error = reedsolomon.decode(codeword, parity_bytes)

    if error:
        return None, error, 0

    payload = repaired[:-1]
    if crc8(payload) != repaired[-1]:
        return None, "crc mismatch after correction", corrected

    return bytes(payload), None, corrected


def frame_byte_count(payload_length, parity_bytes=PARITY_BYTES):
    return LENGTH_COPIES + payload_length + 1 + parity_bytes


def frame_symbol_count(payload_length, parity_bytes=PARITY_BYTES):
    return 4 * frame_byte_count(payload_length, parity_bytes)
