import sounddevice as sd


def same_api_pair(preferred_output="speakers"):
    devices = sd.query_devices()
    apis = sd.query_hostapis()

    best = None
    for index, source in enumerate(devices):
        if source["max_input_channels"] < 1:
            continue

        for out_index, sink in enumerate(devices):
            if sink["max_output_channels"] < 1 or sink["hostapi"] != source["hostapi"]:
                continue

            score = (preferred_output in sink["name"].lower(),
                     apis[source["hostapi"]]["name"] == "MME")

            if best is None or score > best[0]:
                best = (score, index, out_index)

    if best is None:
        raise SystemExit(
            "no input and output on the same host API — a duplex stream needs both\n"
            "on the same one. Run audiocheck to see what is available."
        )

    return best[1], best[2]


def name_of(index):
    return sd.query_devices(index)["name"]
