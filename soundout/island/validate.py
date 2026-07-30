from .situation import ACCESS, FIELDS, NEEDS

LIMITS = {name: (1 << bits) - 1 for name, bits in FIELDS}


class Invalid(ValueError):
    pass


def whole_number(value, name, maximum, minimum=0):
    if isinstance(value, bool):
        raise Invalid(f"{name} must be a whole number, not a true/false value")

    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be a whole number, got {value!r}")

    if number < minimum:
        raise Invalid(f"{name} cannot be less than {minimum}, got {number}")

    if number > maximum:
        raise Invalid(f"{name} cannot be more than {maximum}, got {number}")

    return number


def field(value, name):
    if name not in LIMITS:
        raise Invalid(f"{name} is not a field of the report")
    return whole_number(value, name, LIMITS[name])


def needs(text):
    if text is None:
        return []

    if isinstance(text, str):
        wanted = [part.strip().lower() for part in text.split(",") if part.strip()]
    else:
        wanted = [str(part).strip().lower() for part in text if str(part).strip()]

    unknown = [name for name in wanted if name not in NEEDS]
    if unknown:
        raise Invalid(
            f"unknown need{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}. "
            f"choose from: {', '.join(NEEDS)}")

    seen = []
    for name in wanted:
        if name not in seen:
            seen.append(name)

    return seen


SELECTABLE_ACCESS = [name for name in ACCESS if name != "reserved"]


def access(text):
    name = str(text or "").strip().lower()

    if name not in SELECTABLE_ACCESS:
        raise Invalid(f"unknown access state {text!r}. "
                      f"choose from: {', '.join(SELECTABLE_ACCESS)}")

    return name


def fraction(value, name, minimum=0.0, maximum=1.0):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be a number, got {value!r}")

    if not minimum <= number <= maximum:
        raise Invalid(f"{name} must be between {minimum} and {maximum}, got {number}")

    return number


def seconds(value, name, minimum=0.1, maximum=3600.0):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be a number of seconds, got {value!r}")

    if not minimum <= number <= maximum:
        raise Invalid(f"{name} must be between {minimum} and {maximum} seconds, got {number}")

    return number


def text_payload(value, limit):
    encoded = str(value).encode("utf-8")

    if not encoded:
        raise Invalid("there is nothing to send")

    if len(encoded) > limit:
        raise Invalid(f"the message is {len(encoded)} bytes, the limit is {limit}")

    return encoded


def audio_device(index, kind):
    if index is None:
        return None

    import sounddevice

    try:
        number = int(index)
    except (TypeError, ValueError):
        raise Invalid(f"{kind} device must be a number, got {index!r}")

    devices = sounddevice.query_devices()

    if not 0 <= number < len(devices):
        raise Invalid(f"there is no device {number}; run audiocheck to list them")

    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    if devices[number][channels] < 1:
        raise Invalid(f"device {number} ({devices[number]['name']}) has no {kind} channels")

    return number


def port(value):
    number = whole_number(value, "port", 65535, 1)

    if number < 1024:
        raise Invalid(f"port {number} needs administrator rights; pick 1024 or above")

    return number
