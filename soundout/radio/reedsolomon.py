PRIMITIVE = 0x11D
FIELD = 256

EXP = [0] * 512
LOG = [0] * FIELD

_x = 1
for _i in range(FIELD - 1):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & FIELD:
        _x ^= PRIMITIVE

for _i in range(FIELD - 1, 512):
    EXP[_i] = EXP[_i - (FIELD - 1)]


def add(a, b):
    return a ^ b


def multiply(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return EXP[(LOG[a] - LOG[b]) % (FIELD - 1)]


def inverse(a):
    if a == 0:
        raise ZeroDivisionError("zero has no inverse in GF(256)")
    return EXP[(FIELD - 1) - LOG[a]]


def power(a, n):
    if a == 0:
        return 0
    return EXP[(LOG[a] * n) % (FIELD - 1)]


def poly_add(p, q):
    result = [0] * max(len(p), len(q))
    for i, value in enumerate(p):
        result[i + len(result) - len(p)] = value
    for i, value in enumerate(q):
        result[i + len(result) - len(q)] ^= value
    return result


def poly_multiply(p, q):
    result = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            result[i + j] ^= multiply(a, b)
    return result


def poly_evaluate(p, x):
    total = 0
    for coefficient in p:
        total = multiply(total, x) ^ coefficient
    return total


def poly_scale(p, scalar):
    return [multiply(c, scalar) for c in p]


def generator(parity_bytes):
    g = [1]
    for i in range(parity_bytes):
        g = poly_multiply(g, [1, power(2, i)])
    return g


def encode(data, parity_bytes):
    if len(data) + parity_bytes > FIELD - 1:
        raise ValueError(f"a codeword cannot exceed {FIELD - 1} bytes")

    g = generator(parity_bytes)
    remainder = list(data) + [0] * parity_bytes

    for i in range(len(data)):
        coefficient = remainder[i]
        if coefficient == 0:
            continue
        for j, gj in enumerate(g):
            remainder[i + j] ^= multiply(gj, coefficient)

    return bytes(data) + bytes(remainder[len(data):])


def syndromes(codeword, parity_bytes):
    return [poly_evaluate(list(codeword), power(2, i)) for i in range(parity_bytes)]


def berlekamp_massey(syndrome):
    locator = [1]
    previous = [1]

    for i in range(len(syndrome)):
        delta = syndrome[i]
        for j in range(1, len(locator)):
            delta ^= multiply(locator[len(locator) - 1 - j], syndrome[i - j])

        previous = previous + [0]

        if delta == 0:
            continue

        if len(previous) > len(locator):
            new_locator = poly_scale(previous, delta)
            previous = poly_scale(locator, inverse(delta))
            locator = new_locator

        locator = poly_add(locator, poly_scale(previous, delta))

    while len(locator) > 1 and locator[0] == 0:
        locator.pop(0)

    return locator


def chien_search(locator, length):
    errors = []
    for position in range(length):
        if poly_evaluate(locator, inverse(power(2, position))) == 0:
            errors.append(length - 1 - position)
    return errors


def forney(syndrome, locator, positions, length):
    omega = poly_multiply(syndrome[::-1], locator)
    omega = omega[len(omega) - len(locator) + 1:]

    derivative = [locator[i] for i in range(len(locator) - 1, -1, -1)][1::2]
    derivative = derivative[::-1]

    magnitudes = {}
    for position in positions:
        x = power(2, length - 1 - position)
        x_inverse = inverse(x)

        numerator = poly_evaluate(omega, x_inverse)
        denominator = poly_evaluate(derivative, multiply(x_inverse, x_inverse))

        if denominator == 0:
            return None

        magnitudes[position] = multiply(x, divide(numerator, denominator))

    return magnitudes


def decode(codeword, parity_bytes):
    if parity_bytes == 0:
        return bytes(codeword), 0, None

    received = list(codeword)
    syndrome = syndromes(received, parity_bytes)

    if max(syndrome) == 0:
        return bytes(received[:-parity_bytes]), 0, None

    locator = berlekamp_massey(syndrome)
    errors_found = len(locator) - 1

    if errors_found > parity_bytes // 2:
        return None, 0, f"too many errors: {errors_found} beyond the limit of {parity_bytes // 2}"

    positions = chien_search(locator, len(received))

    if len(positions) != errors_found:
        return None, 0, "error locations could not be resolved"

    magnitudes = forney(syndrome, locator, positions, len(received))
    if magnitudes is None:
        return None, 0, "error magnitudes could not be resolved"

    for position, magnitude in magnitudes.items():
        received[position] ^= magnitude

    if max(syndromes(received, parity_bytes)) != 0:
        return None, 0, "correction did not clear the syndromes"

    return bytes(received[:-parity_bytes]), len(positions), None


def correctable(parity_bytes):
    return parity_bytes // 2
