CRC_POLYNOMIAL = 0x07
MAX_PAYLOAD = 255


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


def build_frame(payload):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload is {len(payload)} bytes, limit is {MAX_PAYLOAD}")

    body = bytes([len(payload)]) + bytes(payload)
    return body + bytes([crc8(body)])


def parse_frame(data):
    if len(data) < 2:
        return None, "frame too short"

    length = data[0]
    expected = 1 + length + 1

    if len(data) < expected:
        return None, f"truncated: need {expected} bytes, have {len(data)}"

    body = data[:1 + length]
    received_crc = data[1 + length]

    if crc8(body) != received_crc:
        return None, "crc mismatch"

    return bytes(body[1:]), None


def frame_symbol_count(payload_length):
    return 4 * (1 + payload_length + 1)
