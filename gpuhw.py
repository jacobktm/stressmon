"""GPU hardware discovery and classification.

Enumerates every display adapter from PCI sysfs, resolves human readable
names from ``lspci``, and classifies each adapter as integrated or discrete
so the UI can label them distinctly and give discrete GPUs precedence.

No third-party dependencies: everything degrades gracefully when ``lspci``
is missing or a sysfs node is unreadable.
"""

import logging
import os
import re
from pathlib import Path
from subprocess import run, PIPE

log = logging.getLogger(__name__)

PCI_DEVICES = Path("/sys/bus/pci/devices")

# PCI display-class codes: VGA controller, 3D controller, 3D programmable
# controller.  Anything else is not a GPU we report on.
GPU_CLASSES = ("030000", "030200", "030300")

VENDOR_LABELS = {
    0x10DE: "NVIDIA",
    0x1002: "AMD",
    0x8086: "Intel",
    0x1A03: "ASPEED",
    0x1234: "QEMU/Bochs",
    0x15AD: "VMware",
    0x1AF4: "VirtIO",
    0x80EE: "VirtualBox",
    0x5853: "Xen",
}

# Names that identify an Intel discrete part (Arc A-series / Battlemage).
_INTEL_DISCRETE_HINTS = ("arc ", "arc(tm)", "arc™", "dg2", "bmg", "g21", "g22")
# APU/integrated Radeon parts are named "Radeon Graphics" with no model
# number, while discrete parts always carry one (RX 7600, Pro W7900, ...).
_AMD_DISCRETE_HINTS = ("radeon rx", "radeon pro", "radeon(tm) rx", "firepro",
                       "instinct", "radeon hd")


def _read(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def _lspci_entries():
    """Return ``{pci_slot: (device name, class name)}`` from lspci -Dmmnn."""
    entries = {}
    try:
        proc = run(["lspci", "-Dmmnn"], stdout=PIPE, stderr=PIPE, timeout=10)
    except (FileNotFoundError, OSError) as e:
        log.debug("lspci unavailable: %s", e)
        return entries
    if proc.returncode != 0:
        return entries
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or not line.startswith("0000:"):
            continue
        parts = line.split('"')
        if len(parts) < 6:
            continue
        slot = parts[0].strip()
        class_name = parts[1].rsplit("[", 1)[0].strip()
        device = parts[5].rsplit("[", 1)[0].strip()
        entries[slot] = (device, class_name)
    return entries


def _lspci_names():
    """Return ``{pci_slot: device name}`` (compatibility helper)."""
    return {slot: dev for slot, (dev, _cls) in _lspci_entries().items()}


def _clean_name(name):
    """Strip vendor prefixes, revision suffixes and bracket ids from lspci."""
    if not name:
        return ""
    text = re.sub(r"\s*\(rev [^)]+\)", "", name)
    text = re.sub(r"\s*\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\]", "", text)
    for prefix in ("Intel Corporation ", "NVIDIA Corporation ",
                   "Advanced Micro Devices, Inc. ", "AMD ",
                   "ATI Technologies Inc. "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip() or name.strip()


def classify(vendor_id, name, vram_mb=None):
    """Classify a GPU as ``'discrete'``, ``'integrated'`` or ``'unknown'``.

    *vram_mb* is the dedicated VRAM size when the driver reports it: APUs
    expose little or none, which is the only reliable AMD signal available
    without root.
    """
    vendor_id &= 0xFFFF
    label = VENDOR_LABELS.get(vendor_id, "")
    low = (name or "").lower()

    if vendor_id == 0x10DE:                      # NVIDIA is discrete-only
        return "discrete"
    if vendor_id == 0x8086:                      # Intel
        if any(hint in low for hint in _INTEL_DISCRETE_HINTS):
            return "discrete"
        return "integrated"
    if vendor_id == 0x1002:                      # AMD
        if vram_mb is not None:
            return "discrete" if vram_mb > 512 else "integrated"
        if any(hint in low for hint in _AMD_DISCRETE_HINTS):
            return "discrete"
        if re.search(r"radeon.*\b(r\d|tph|navi|vega|barcelo|van gogh|phoenix|"
                     r"strix|dragon range|hawk point)\b", low):
            return "integrated"
        return "integrated" if "graphics" in low else "unknown"
    if vendor_id in (0x1AF4, 0x15AD, 0x1234, 0x5853, 0x80EE):
        return "virtual"
    if not label:
        return "unknown"
    return "integrated"


def drm_card_map():
    """Return ``{pci_slot: /sys/class/drm cardN}`` for bound display devices."""
    cards = {}
    drm = Path("/sys/class/drm")
    if not drm.is_dir():
        return cards
    for entry in sorted(drm.iterdir()):
        if not entry.name.startswith("card") or "-" in entry.name:
            continue
        try:
            slot = Path(os.path.realpath(entry / "device")).name
        except OSError:
            continue
        if slot:
            cards[slot] = entry
    return cards


def intel_telemetry(card):
    """Read i915 frequency/power data for an Intel iGPU (best effort)."""
    out = {}
    if not card:
        return out
    card = Path(card)
    for key, path in (("clock", "gt_cur_freq_mhz"),
                      ("clock_max", "gt_max_freq_mhz"),
                      ("clock_min", "gt_min_freq_mhz"),
                      ("rc6_ms", "gt/gt0/rc6_residency_ms"),
                      ("power_watts", "power/act_now")):
        raw = _read(card / path)
        if raw:
            try:
                out[key] = float(raw)
            except ValueError:
                pass
    return out


def _drm_driver(card):
    return _read(card / "device" / "driver").rsplit("/", 1)[-1] if card else ""


def discover():
    """Return a list of dicts describing every display adapter found.

    Keys: ``slot`` (PCI address), ``vendor_id``/``device_id``, ``vendor``
    (labelled name), ``pci_name``, ``name``, ``kind``, ``driver``, ``card``
    (DRM node) and ``vendor_key`` (``nvidia``/``amdgpu``/``intel``/``other``).
    Entries are sorted discrete-first, then by PCI slot, so callers can use
    the order directly.
    """
    entries = _lspci_entries()
    cards = drm_card_map()
    gpus = []
    if not PCI_DEVICES.is_dir():
        return gpus

    for dev in sorted(PCI_DEVICES.iterdir()):
        uevent = _read(dev / "uevent")
        fields = dict(line.split("=", 1) for line in uevent.splitlines() if "=" in line)
        pci_class = (fields.get("PCI_CLASS") or _read(dev / "class")).lower()
        pci_class = pci_class[2:] if pci_class.startswith("0x") else pci_class
        if pci_class.zfill(6) not in GPU_CLASSES:
            continue
        pci_id = fields.get("PCI_ID", "")
        vendor_hex, _, device_hex = pci_id.partition(":")
        if not vendor_hex:
            continue
        try:
            vendor_id = int(vendor_hex, 16)
            device_id = int(device_hex, 16)
        except ValueError:
            continue
        slot = fields.get("PCI_SLOT_NAME", dev.name)
        driver = fields.get("DRIVER", "")
        card = cards.get(slot)
        if not driver and card is not None:
            driver = _drm_driver(card)
        pci_name, class_name = entries.get(slot, ("", ""))
        pci_name = _clean_name(pci_name)
        vendor_label = VENDOR_LABELS.get(vendor_id, f"0x{vendor_hex}")

        if driver.startswith("nvidia") or vendor_id == 0x10DE:
            vendor_key = "nvidia"
        elif driver.startswith("amdgpu") or vendor_id == 0x1002:
            vendor_key = "amdgpu"
        elif driver.startswith("i915") or driver.startswith("xe") or vendor_id == 0x8086:
            vendor_key = "intel"
        else:
            vendor_key = "other"

        gpus.append({
            "slot": slot,
            "vendor_id": vendor_id,
            "device_id": device_id,
            "vendor": vendor_label,
            "vendor_key": vendor_key,
            "pci_name": pci_name,
            "name": pci_name or f"{vendor_label} GPU {device_id:04x}",
            "class": class_name,
            "driver": driver,
            "card": str(card) if card is not None else None,
            "subsystem": fields.get("PCI_SUBSYS_ID", ""),
            "kind": "unknown",
            "intel": intel_telemetry(card) if vendor_key == "intel" else {},
        })

    for gpu in gpus:
        gpu["kind"] = classify(gpu["vendor_id"], gpu["name"])
    gpus.sort(key=lambda g: (0 if g["kind"] == "discrete" else 1,
                             0 if g["kind"] == "integrated" else 1,
                             g["slot"]))
    return gpus


# Re-exported for callers that only need a stable ordering key.
KIND_ORDER = {"discrete": 0, "integrated": 1, "virtual": 2, "unknown": 3}


def kind_rank(kind):
    return KIND_ORDER.get(kind, 9)
