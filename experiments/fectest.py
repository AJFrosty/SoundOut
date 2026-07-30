import random

from soundout.radio.reedsolomon import (
    FIELD,
    correctable,
    decode,
    divide,
    encode,
    inverse,
    multiply,
)

RANDOM = random.Random(17)


def field_axioms():
    print("is GF(256) actually a field?")

    elements = list(range(FIELD))
    nonzero = elements[1:]

    closed = all(0 <= multiply(a, b) < FIELD
                 for a in RANDOM.sample(elements, 40) for b in RANDOM.sample(elements, 40))
    print(f"  closure under multiply     : {'yes' if closed else 'NO'}")

    identity = all(multiply(a, 1) == a for a in elements)
    print(f"  1 is the identity          : {'yes' if identity else 'NO'}")

    inverses = all(multiply(a, inverse(a)) == 1 for a in nonzero)
    print(f"  every nonzero has inverse  : {'yes' if inverses else 'NO'}")

    commutes = all(multiply(a, b) == multiply(b, a)
                   for a in RANDOM.sample(elements, 30) for b in RANDOM.sample(elements, 30))
    print(f"  multiplication commutes    : {'yes' if commutes else 'NO'}")

    associates = all(
        multiply(multiply(a, b), c) == multiply(a, multiply(b, c))
        for a in RANDOM.sample(nonzero, 15)
        for b in RANDOM.sample(nonzero, 15)
        for c in RANDOM.sample(nonzero, 15))
    print(f"  multiplication associates  : {'yes' if associates else 'NO'}")

    distributes = all(
        multiply(a, b ^ c) == multiply(a, b) ^ multiply(a, c)
        for a in RANDOM.sample(elements, 25)
        for b in RANDOM.sample(elements, 25)
        for c in RANDOM.sample(elements, 25))
    print(f"  multiply distributes over + : {'yes' if distributes else 'NO'}")

    divides = all(multiply(divide(a, b), b) == a
                  for a in RANDOM.sample(elements, 30) for b in RANDOM.sample(nonzero, 30))
    print(f"  division undoes multiply   : {'yes' if divides else 'NO'}")


def clean_round_trip(parity=6):
    print(f"\nencode and decode with no damage ({parity} parity bytes)")
    message = bytes(RANDOM.getrandbits(8) for _ in range(16))

    codeword = encode(message, parity)
    recovered, corrected, error = decode(codeword, parity)

    print(f"  message {len(message)} bytes -> codeword {len(codeword)} bytes")
    print(f"  systematic (message visible in codeword): {codeword[:16] == message}")
    print(f"  recovered exactly: {recovered == message}, corrections {corrected}, error {error}")


def correction_capability(parity=6, trials=300):
    limit = correctable(parity)
    print(f"\ndamage tolerance with {parity} parity bytes (limit is {limit} bad bytes)")
    print("  bytes damaged   recovered   detected as too damaged   WRONG ANSWER")

    for damaged in range(0, limit + 3):
        recovered = 0
        detected = 0
        wrong = 0

        for _ in range(trials):
            message = bytes(RANDOM.getrandbits(8) for _ in range(16))
            codeword = bytearray(encode(message, parity))

            for position in RANDOM.sample(range(len(codeword)), damaged):
                codeword[position] ^= RANDOM.randint(1, 255)

            result, _, error = decode(bytes(codeword), parity)

            if error is not None:
                detected += 1
            elif result == message:
                recovered += 1
            else:
                wrong += 1

        flag = "  <-- limit" if damaged == limit else ""
        print(f"  {damaged:13d}   {recovered / trials:9.0%}   {detected / trials:23.0%}   "
              f"{wrong / trials:12.0%}{flag}")


def burst_damage(parity=6, trials=300):
    print(f"\nconsecutive damage, which is what a squelch click looks like")
    print("  burst length   recovered")

    for length in range(0, correctable(parity) + 2):
        recovered = 0

        for _ in range(trials):
            message = bytes(RANDOM.getrandbits(8) for _ in range(16))
            codeword = bytearray(encode(message, parity))

            if length:
                start = RANDOM.randint(0, len(codeword) - length)
                for position in range(start, start + length):
                    codeword[position] ^= RANDOM.randint(1, 255)

            result, _, error = decode(bytes(codeword), parity)
            if error is None and result == message:
                recovered += 1

        print(f"  {length:12d}   {recovered / trials:9.0%}")


def airtime_cost():
    print("\nwhat the protection costs in airtime")
    print("  parity   corrects   payload+parity   extra airtime")

    for parity in (0, 4, 6, 8, 10):
        total = 16 + parity
        extra = parity * 4 * 0.02
        print(f"  {parity:6d}   {correctable(parity):8d}   {total:13d}   +{extra:.2f} s")


if __name__ == "__main__":
    field_axioms()
    clean_round_trip()
    correction_capability()
    burst_damage()
    airtime_cost()
