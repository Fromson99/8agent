# Embedded into the final standalone notebook TXT by build.py.
TRANSPORT_R3_SOURCE = __TRANSPORT_SOURCE__
TRANSPORT_R3_SHA256 = __TRANSPORT_SHA256__
SERVICE_R2_SHA256 = __SERVICE_SHA256__


def prepare_client_r3(base, work):
    """Keep sealed R1 intact; derive an auditable R3 client in another code folder."""
    code = safe_path(work / "code-r3" / CLIENT_NAME)
    base_pins = json.loads((base / "CODE_PINS.json").read_text())
    transport = TRANSPORT_R3_SOURCE.encode("utf-8")
    if hashlib.sha256(transport).hexdigest() != TRANSPORT_R3_SHA256:
        raise RunError("RUNNER_TRANSPORT_HASH")
    files = {}
    for name, expected in base_pins["files"].items():
        data = (base / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RunError("BASE_CLIENT_CHANGED: " + name)
        if name == "transport.py":
            data = transport
        elif name == "SERVICE_CODE_SHA256.txt":
            data = (SERVICE_R2_SHA256 + "\n").encode("ascii")
        files[name] = data
    pins = {"format": "pipeline-code-pins-v1", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["CODE_PINS.json"] = (json.dumps(pins, sort_keys=True, indent=2) + "\n").encode()
    for name, data in files.items():
        target = safe_path(code / name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != data:
                raise RunError("CLIENT_R3_CHANGED: " + name)
        else:
            temp = safe_path(target.with_name(".r3-install.tmp"))
            with temp.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
    binding = {"base_zip_sha256": CLIENT_SHA256, "transport_sha256": TRANSPORT_R3_SHA256,
               "service_sha256": SERVICE_R2_SHA256,
               "client_code_pins_sha256": hashlib.sha256(files["CODE_PINS.json"]).hexdigest()}
    marker = safe_path(work / "client-r3-binding.json")
    if marker.exists() and json.loads(marker.read_text()) != binding:
        raise RunError("CLIENT_R3_BINDING_CHANGED")
    if not marker.exists():
        save_json(marker, binding)
    return code
