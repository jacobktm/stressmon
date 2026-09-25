"""Module for GPU Data

Supports any number of GPUs, including systems with both an integrated and
a discrete adapter.  Each GPU is classified as integrated or discrete by
:mod:`stressmon.gpuhw`, and discrete GPUs always sort first so they take
precedence in the monitor.
"""

import logging
from subprocess import run, PIPE, CalledProcessError
from psutil import sensors_fans
from pyamdgpuinfo import detect_gpus, get_gpu
from pynvml import nvmlInit, NVMLError, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,   \
    nvmlDeviceGetName, nvmlDeviceGetPowerManagementLimit, nvmlShutdown,    \
    nvmlDeviceGetFanSpeed, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU, \
    nvmlDeviceGetPowerUsage, nvmlDeviceGetUtilizationRates,                \
    nvmlSystemGetDriverVersion, nvmlDeviceGetClock, NVML_CLOCK_GRAPHICS,   \
    NVML_CLOCK_ID_CURRENT, nvmlDeviceGetMemoryInfo, nvmlDeviceGetPciInfo, \
    nvmlDeviceGetPowerManagementLimitConstraints
from stressmon import gpuhw
from stressmon.hwsensors import HWSensorBase

log = logging.getLogger(__name__)

KIND_LABELS = {
    'discrete': 'dGPU',
    'integrated': 'iGPU',
    'virtual': 'vGPU',
    'unknown': 'GPU',
}


def _nvml_name(handle):
    try:
        return nvmlDeviceGetName(handle)
    except NVMLError:
        return None


def _nvml_driver_version():
    try:
        return nvmlSystemGetDriverVersion()
    except NVMLError:
        return None


class GPUData(HWSensorBase):
    """Class to manage GPU Data.

    This class inherits from HWSensorBase and provides functionality to collect and manage GPU
    data such as temperature, clock speed, fan speed, power consumption, and utilization.

    Attributes:
        vendors (list): List of detected GPU vendors.
        gpus (dict): Dictionary containing GPU data.
        iteration (int): Counter for the number of data update iterations.
        data (list): List of supported GPU data types.
        lines (int): Number of lines needed for this data's curses window.
        indexes (list): Indexes used for iteration.
    """

    headings = ['Data', 'Current', 'Min', 'Max', 'Mean']
    VENDOR_ORDER = ['nvidia', 'amdgpu', 'intel', 'other']

    def __init__(self) -> None:
        self.vendor_iter = None
        self.name_iter = None
        self.data_iter = None
        self.current_vendor = None
        self.current_name = None
        self.vendors = []
        self.gpus = {}
        self.hw_list = []          # every adapter found, discrete first
        self.kind = {}             # (vendor, name) -> 'discrete'/'integrated'/...
        self.fan_units = {}        # (vendor, name) -> '%' (nvidia) or 'RPM'
        self.fan_sources = {}      # (vendor, name) -> 'driver' or 'acpi'
        self.fan_labels = {}       # (vendor, name) -> hwmon label of that fan
        self.slot = {}             # (vendor, name) -> PCI slot
        self.mem_limits = {}       # (vendor, name) -> dedicated VRAM in GB
        self.intel_cards = {}      # name -> sysfs card node for the iGPU
        self.handle_by_name = {}   # name -> NVML handle
        self.gpuinfo_by_name = {}  # name -> pyamdgpuinfo object
        self.iteration = 1
        self.data = ['temp', 'clock', 'fan_speed', 'power', 'memory', 'utilization']
        self.lines = 1

        # Enumerate every display adapter (both iGPU and dGPU) and classify it.
        try:
            self.hw_list = gpuhw.discover()
        except Exception as e:  # never let discovery break monitoring
            log.debug("GPU discovery failed: %s", e)
            self.hw_list = []

        nvml_handles = self._init_nvidia()
        amd_gpus = self._init_amdgpu()
        self._init_intel()

        # min/max/mean accumulators: built explicitly rather than deep-copied,
        # since NVML handles and pyamdgpuinfo objects are not copyable.
        self.mmm = {}
        for vendor in self.vendors:
            self.mmm[vendor] = {'names': list(self.gpus[vendor]['names'])}
            for name in self.mmm[vendor]['names']:
                self.mmm[vendor][name] = {d: [999999, 0, 0] for d in self.data}
        self._order_gpus()

    # ── setup helpers ──────────────────────────────────────────────

    def _hw_by_slot(self, slot):
        for gpu in self.hw_list:
            if gpu.get("slot") == slot:
                return gpu
        return {}

    def _hw_for_vendor(self, vendor_key):
        return [g for g in self.hw_list if g.get("vendor_key") == vendor_key]

    def _register(self, vendor, name, kind, fan_unit=None, slot="", mem_limit=None):
        """Create the per-GPU record and remember its classification."""
        self.gpus[vendor][name] = {
            'temp': None, 'clock': None, 'fan_speed': None, 'power': None,
            'power_limit': None, 'memory': None, 'mem_limit': mem_limit,
            'utilization': None, 'subsysven': None,
        }
        self.kind[(vendor, name)] = kind or 'unknown'
        self.fan_units[(vendor, name)] = fan_unit or 'RPM'
        self.fan_sources[(vendor, name)] = None
        self.fan_labels[(vendor, name)] = None
        self.slot[(vendor, name)] = slot
        self.mem_limits[(vendor, name)] = mem_limit
        self.gpus[vendor]['names'].append(name)

    def _system_fan(self, kind):
        """Return (label, rpm) for the chassis fan a GPU is cooled by.

        Laptop GPUs frequently have no fan of their own: NVML reports
        "Not Supported" and the cooling is done by a system fan that the
        firmware exposes through ACPI/hwmon ("GPU fan").  Those sensors
        report RPM, never a duty-cycle percentage.
        """
        if kind != 'discrete':
            return None, None
        wanted = ('gpu', 'dgpu', 'graphics')
        for chip, entries in sensors_fans().items():
            for entry in entries:
                label = (entry.label or '').lower()
                if any(key in label for key in wanted):
                    return f"{chip} {entry.label or ''}".strip(), entry.current
        return None, None

    def _fallback_fan(self, vendor, gpu_name, kind):
        """Fill a missing GPU fan from the system fan, in RPM."""
        if self.fan_sources.get((vendor, gpu_name)) == 'driver':
            return None
        label, rpm = self._system_fan(kind)
        if label is None:
            return None
        self.fan_units[(vendor, gpu_name)] = 'RPM'
        self.fan_sources[(vendor, gpu_name)] = 'acpi'
        self.fan_labels[(vendor, gpu_name)] = label
        if self.iteration == 1:
            self.lines += 1
        return rpm

    def _init_nvidia(self):
        """Attach NVML telemetry, matching handles to discovered adapters."""
        try:
            nvmlInit()
        except NVMLError:
            return []
        handles = []
        drivers = [g for g in self._hw_for_vendor('nvidia')]
        self.vendors.append('nvidia')
        self.gpus['nvidia'] = {'names': [], 'handles': []}
        self.gpus['nvidia']['driver_version'] = _nvml_driver_version()
        self.lines += 1
        for index in range(nvmlDeviceGetCount()):
            handle = nvmlDeviceGetHandleByIndex(index)
            handles.append(handle)
            nvml_name = _nvml_name(handle)
            slot = ''
            try:
                slot = nvmlDeviceGetPciInfo(handle).busId.lower()
            except NVMLError:
                pass
            hw = self._hw_by_slot(slot) if slot else {}
            # Fall back to positional matching when the bus id is unavailable.
            if not hw and index < len(drivers):
                hw = drivers[index]
            name = f"{nvml_name or hw.get('name', 'NVIDIA GPU')}-{index}"
            power_limit = None
            try:
                power_limit = nvmlDeviceGetPowerManagementLimit(handle) / 1000
            except NVMLError:
                # Laptops often report no enforced limit; fall back to the
                # board's maximum so the inventory still shows a TDP figure.
                try:
                    _min_w, max_w = nvmlDeviceGetPowerManagementLimitConstraints(handle)
                    power_limit = max_w / 1000 or None
                except NVMLError:
                    power_limit = None
            try:
                mem_mb = nvmlDeviceGetMemoryInfo(handle).total / 1024 / 1024
            except NVMLError:
                mem_mb = None
            # NVIDIA is always discrete; its "fan speed" is a duty-cycle %.
            self._register('nvidia', name, 'discrete', fan_unit='%',
                           slot=hw.get('slot', slot), mem_limit=mem_mb)
            self.handle_by_name[name] = handle
            self.gpus['nvidia'][name]['power_limit'] = power_limit
            self.gpus['nvidia'][name]['subsysven'] = hw.get('subsystem') or None
            self.lines += 8
        self.gpus['nvidia']['handles'] = handles
        return handles

    def _init_amdgpu(self):
        """Attach pyamdgpuinfo telemetry for every AMD adapter."""
        try:
            amd_count = detect_gpus()
        except Exception:
            amd_count = 0
        if not amd_count:
            return []
        self.vendors.append('amdgpu')
        self.gpus['amdgpu'] = {'names': [], 'gpuinfos': []}
        self.lines += 1
        adapters = self._hw_for_vendor('amdgpu')
        for index in range(amd_count):
            try:
                gpuinfo = get_gpu(index)
            except Exception:
                continue
            hw = adapters[index] if index < len(adapters) else {}
            display = gpuinfo.name or hw.get('name') or f"AMD GPU {index}"
            name = f"{display}-{index}"
            try:
                vram_mb = round(gpuinfo.memory_info['vram_size'] / 1024 / 1024, 2)
            except Exception:
                vram_mb = None
            kind = gpuhw.classify(0x1002, display, vram_mb)
            self._register('amdgpu', name, kind, fan_unit='RPM',
                           slot=hw.get('slot', ''), mem_limit=vram_mb)
            self.gpus['amdgpu'][name]['subsysven'] = hw.get('subsystem') or None
            self.gpus['amdgpu']['gpuinfos'].append(gpuinfo)
            self.gpuinfo_by_name[name] = gpuinfo
            self.lines += 7
        return self.gpus['amdgpu']['gpuinfos']

    def _init_intel(self):
        """Expose Intel iGPUs through the i915 sysfs frequency nodes."""
        adapters = self._hw_for_vendor('intel')
        if not adapters:
            return
        self.vendors.append('intel')
        self.gpus['intel'] = {'names': [], 'cards': []}
        self.lines += 1
        for index, hw in enumerate(adapters):
            display = hw.get('name') or f"Intel GPU {index}"
            name = f"{display}-{index}"
            self._register('intel', name, 'integrated', fan_unit='RPM',
                           slot=hw.get('slot', ''))
            self.gpus['intel'][name]['subsysven'] = hw.get('subsystem') or None
            self.gpus['intel']['cards'].append(hw.get('card'))
            self.intel_cards[name] = hw.get('card')
            self.lines += 7

    def _order_gpus(self):
        """Order every vendor's GPU list so discrete GPUs come first."""
        for vendor in self.vendors:
            names = self.gpus[vendor].get('names', [])
            names.sort(key=lambda n: (gpuhw.kind_rank(self.kind.get((vendor, n))),
                                      self.slot.get((vendor, n), ''), n))
            self.gpus[vendor]['names'] = names

    def __del__(self) -> None:
        if 'nvidia' in self.vendors:
            nvmlShutdown()

    def __iter__(self):
        # Vendors are visited in the order their first GPU ranks, so a
        # discrete GPU is always presented before an integrated one.
        self.vendor_iter = iter(self.get_vendor_order())
        self._next_vendor()
        return self

    def get_vendor_order(self) -> list:
        """Return vendor keys ordered by their best GPU's kind."""
        return sorted(self.vendors, key=lambda v: (
            min((gpuhw.kind_rank(self.kind.get((v, n))) for n in
                 self.gpus.get(v, {}).get('names', [])), default=9),
            self.VENDOR_ORDER.index(v) if v in self.VENDOR_ORDER else 9))

    def _next_vendor(self):
        self.current_vendor = next(self.vendor_iter, None)
        if self.current_vendor:
            self.name_iter = iter(self.gpus[self.current_vendor]['names'])
            self._next_name()

    def _next_name(self):
        self.current_name = next(self.name_iter, None)
        if self.current_name:
            self.data_iter = iter(self.data)

    def __next__(self) -> list:
        if not self.current_vendor:
            raise StopIteration

        try:
            return [self.current_vendor, self.current_name, next(self.data_iter)]
        except StopIteration:
            try:
                self._next_name()
                return [self.current_vendor, self.current_name, next(self.data_iter)]
            except StopIteration:
                self._next_vendor()
                if not self.current_vendor:
                    raise
                return [self.current_vendor, self.current_name, next(self.data_iter)]

    def get_label(self, params: list) -> str | None:
        """Get label for current gpu's current data"""
        if len(params) != 3:
            return None
        return params[2]

    def get_section(self, params: list) -> str | None:
        """Get section"""
        if len(params) != 3:
            return None
        return f"{params[0]}"

    def get_subsection(self, params: list) -> str | None:
        """Get subsection"""
        if len(params) != 3:
            return None
        return f"{params[1]}"

    def get_vendors(self) -> list:
        """Get list of vendors for detected GPUs

        Returns:
            list: list of detected GPU vendors
        """
        return self.vendors

    def get_gpu_names(self, vendor: str) -> list:
        """Get list of GPU's for given vendor

        Args:
            vendor (str): vendor name

        Returns:
            list: list of detected GPUs
        """
        gpus = self.gpus.get(vendor, {})
        return gpus.get('names', [])

    def get_dataset(self) -> list:
        """get the supported dataset

        Returns:
            list: dataset list
        """
        return self.data

    def update_mmm(self, vendor: str, name: str, data: str, current: float):
        """Update the min, man, mean data
        """
        minimum = self.mmm[vendor][name][data][0]
        maximum = self.mmm[vendor][name][data][1]
        mean = self.mmm[vendor][name][data][2]
        self.mmm[vendor][name][data][0] = min([minimum, current])
        self.mmm[vendor][name][data][1] = max([maximum, current])
        self.mmm[vendor][name][data][2] = mean + \
            (current - mean) / self.iteration

    def update(self) -> None:
        """Update GPU Info"""

        for vendor, gpu_data in self.gpus.items():
            for gpu_name in gpu_data['names']:
                if vendor == 'nvidia':
                    handle = self.handle_by_name.get(gpu_name)
                    if handle is None:
                        continue
                    fan_speed = None
                    try:
                        # NVML reports fan speed as a duty cycle percentage.
                        fan_speed = nvmlDeviceGetFanSpeed(handle)
                        if self.iteration == 1:
                            self.lines += 1
                    except NVMLError:
                        pass
                    if fan_speed is not None:
                        self.fan_sources[(vendor, gpu_name)] = 'driver'
                    else:
                        fan_speed = self._fallback_fan(
                            vendor, gpu_name, self.kind.get((vendor, gpu_name)))

                    self.gpus[vendor][gpu_name]['temp'] = nvmlDeviceGetTemperature(
                        handle,
                        NVML_TEMPERATURE_GPU)
                    self.gpus[vendor][gpu_name]['clock'] = nvmlDeviceGetClock(handle,
                                                                              NVML_CLOCK_GRAPHICS,
                                                                              NVML_CLOCK_ID_CURRENT)
                    self.gpus[vendor][gpu_name]['fan_speed'] = fan_speed
                    self.gpus[vendor][gpu_name]['power'] = nvmlDeviceGetPowerUsage(
                        handle) / 1000
                    self.gpus[vendor][gpu_name]['memory'] = round(
                        (nvmlDeviceGetMemoryInfo(handle).used / 1024 / 1024), 2)
                    self.gpus[vendor][gpu_name]['utilization'] = nvmlDeviceGetUtilizationRates(
                        handle).gpu

                elif vendor == 'amdgpu':
                    gpuinfo = self.gpuinfo_by_name.get(gpu_name)
                    if gpuinfo is None:
                        continue
                    fan_speed = None
                    fans = sensors_fans()
                    if 'amdgpu' in fans.keys():
                        try:
                            # amdgpu hwmon reports fan speed in RPM.
                            fan_speed = fans['amdgpu'][gpuinfo.gpu_id][1]
                            if self.iteration == 1:
                                self.lines += 1
                        except (IndexError, KeyError, TypeError):
                            pass
                    if fan_speed is not None:
                        self.fan_sources[(vendor, gpu_name)] = 'driver'
                    else:
                        fan_speed = self._fallback_fan(
                            vendor, gpu_name, self.kind.get((vendor, gpu_name)))

                    self.gpus[vendor][gpu_name]['temp'] = gpuinfo.query_temperature()
                    self.gpus[vendor][gpu_name]['fan_speed'] = fan_speed
                    self.gpus[vendor][gpu_name]['power'] = gpuinfo.query_power()
                    self.gpus[vendor][gpu_name]['memory'] = round(
                        (gpuinfo.query_vram_usage() / 1024 / 1024), 2)
                    self.gpus[vendor][gpu_name]['utilization'] = gpuinfo.query_load(
                    ) * 100

                elif vendor == 'intel':
                    card = self.intel_cards.get(gpu_name)
                    telemetry = gpuhw.intel_telemetry(card)
                    self.gpus[vendor][gpu_name]['clock'] = telemetry.get('clock')
                    self.gpus[vendor][gpu_name]['power'] = telemetry.get('power_watts')
                    # Intel iGPUs report no temperature, fan or VRAM data, and
                    # the chassis fan that cools them is not a GPU fan.
                    self.gpus[vendor][gpu_name]['temp'] = None
                    self.gpus[vendor][gpu_name]['fan_speed'] = None
                    self.gpus[vendor][gpu_name]['memory'] = None
                    self.gpus[vendor][gpu_name]['utilization'] = None

                for data in self.data:
                    current = self.gpus[vendor][gpu_name][data]
                    if current is not None:
                        self.update_mmm(vendor, gpu_name, data, current)
            self.lines += 1

        self.iteration += 1

    def get_power_limit(self, vendor: str, name: str) -> int:
        """get power limit for gpu given vendor and gpu name

        Args:
            vendor (str): name of gpu vendor
            name (str): name of gpu

        Returns:
            int: power limit for gpu
        """
        gpus = self.gpus.get(vendor, {})
        gpu = gpus.get(name, {})
        ret = gpu.get('power_limit', None)
        if ret is not None:
            ret = round(ret)
        return ret

    def get_subven(self, vendor: str, name: str) -> str:
        """get subsystem vendor for gpu given vendor and gpu name

        Args:
            vendor (str): name of gpu vendor
            name (str): name of gpu

        Returns:
            str: name of the subsystem vendor
        """
        gpus = self.gpus.get(vendor, {})
        gpu = gpus.get(name, {})
        return gpu.get('subsysven', None)

    def get_driver_version(self) -> str | None:
        """If NVIDIA return driver version

        Returns:
            str | None: driver version or None
        """
        if 'nvidia' in self.vendors:
            return nvmlSystemGetDriverVersion()
        return None

    def get_current(self, params: list) -> int | None:
        """get current value of data for gpu given vendor and gpu name

        Args:
            vendor (str): gpu vendor
            name (str): gpu name
            data (str): data being queried

        Returns:
            int: returns current value for data
        """
        if len(params) != 3:
            return None
        ret = self.gpus.get(params[0], {}).get(
            params[1], {}).get(params[2], None)
        if ret is None:
            return ret
        return round(ret)

    def get_min(self, params: list) -> int | None:
        """Get minimum value of data for gpu given vendor and gpu name

        Args:
            vendor (str): gpu vendor
            name (str): gpu name_
            data (str): data being queried

        Returns:
            int: return minimum value for data
        """
        if len(params) != 3:
            return None
        vendor = self.mmm.get(params[0], {})
        name = vendor.get(params[1], {})
        data = name.get(params[2], None)
        if data is None:
            return data
        return round(data[0])

    def get_max(self, params: list) -> int | None:
        """Get maximum value of data for gpu given vendor and gpu name

        Args:
            vendor (str): gpu vendor
            name (str): gpu name
            data (str): data being queried

        Returns:
            int: return maximum value for data
        """
        if len(params) != 3:
            return None
        ret = self.mmm.get(params[0], {}).get(
            params[1], {}).get(params[2], [None, None, None])[1]
        if ret is None:
            return ret
        return round(ret)

    def get_mean(self, params: list) -> int | None:
        """Get mean value of data for gpu given vendor and gpu name

        Args:
            vendor (str): gpu vendor
            name (str): gpu name_
            data (str): data being queried

        Returns:
            int: return mean value for data
        """
        if len(params) != 3:
            return None
        ret = self.mmm.get(params[0], {}).get(
            params[1], {}).get(params[2], [None, None, None])[2]
        if ret is None:
            return ret
        return round(ret)

    # ── multi-GPU helpers ─────────────────────────────────────────

    def get_gpu_kind(self, vendor: str, name: str) -> str:
        """Return ``'discrete'``/``'integrated'``/``'virtual'`` for a GPU."""
        return self.kind.get((vendor, name), 'unknown')

    def get_kind_label(self, vendor: str, name: str) -> str:
        """Return the short label shown in the UI (dGPU/iGPU)."""
        return KIND_LABELS.get(self.get_gpu_kind(vendor, name), 'GPU')

    def get_fan_source(self, vendor: str, name: str) -> str | None:
        """Return 'driver' for a fan the GPU driver reports, 'acpi' when the
        reading comes from the system fan that cools this GPU, else None."""
        return self.fan_sources.get((vendor, name))

    def get_fan_label(self, vendor: str, name: str) -> str | None:
        """Return the hwmon label of the fan backing this GPU's reading."""
        return self.fan_labels.get((vendor, name))

    def get_fan_unit(self, vendor: str, name: str) -> str:
        """Return the fan-speed unit for a GPU.

        NVIDIA reports a duty-cycle percentage; amdgpu hwmon reports RPM.
        """
        return self.fan_units.get((vendor, name), 'RPM')

    def get_slot(self, vendor: str, name: str) -> str:
        """Return the PCI slot address for a GPU."""
        return self.slot.get((vendor, name), '')

    def get_mem_limit(self, vendor: str, name: str) -> float | None:
        """Return the dedicated VRAM size in MB, if known."""
        return self.mem_limits.get((vendor, name))

    def get_display_name(self, vendor: str, name: str) -> str:
        """Return the GPU name without the trailing index suffix."""
        return name.rsplit('-', 1)[0] if '-' in name else name

    def _build_inventory(self) -> list:
        """Build the per-GPU entry list, discrete first (no primary flag)."""
        entries = []
        for vendor in self.get_vendor_order():
            vendor_data = self.gpus.get(vendor, {})
            driver_version = vendor_data.get('driver_version')
            for name in vendor_data.get('names', []):
                kind = self.get_gpu_kind(vendor, name)
                values = {}
                for metric in self.data:
                    raw = vendor_data.get(name, {}).get(metric)
                    values[metric] = round(raw, 4) if isinstance(raw, (int, float)) else None
                entries.append({
                    'vendor': vendor,
                    'name': name,
                    'display': self.get_display_name(vendor, name),
                    'kind': kind,
                    'kind_label': KIND_LABELS.get(kind, 'GPU'),
                    'slot': self.get_slot(vendor, name),
                    'fan_unit': self.get_fan_unit(vendor, name),
                    'fan_source': self.get_fan_source(vendor, name),
                    'fan_label': self.get_fan_label(vendor, name),
                    'vram_mb': self.get_mem_limit(vendor, name),
                    'power_limit': self.get_power_limit(vendor, name),
                    'subsysven': self.get_subven(vendor, name),
                    'driver_version': driver_version,
                    'monitored': True,
                    'data': values,
                })
        entries.extend(self._unmonitored(entries))
        return entries

    def _unmonitored(self, entries):
        """Return discovered adapters that have no live telemetry.

        These are still reported so every GPU the machine has shows up in
        the monitor and the report, even when no driver exposes readings.
        """
        known = {e.get('slot') for e in entries if e.get('slot')}
        extra = []
        for hw in self.hw_list:
            slot = hw.get('slot')
            if not slot or slot in known:
                continue
            kind = hw.get('kind', 'unknown')
            extra.append({
                'vendor': hw.get('vendor_key', 'other'),
                'name': hw.get('name', 'GPU'),
                'display': hw.get('name', 'GPU'),
                'kind': kind,
                'kind_label': KIND_LABELS.get(kind, 'GPU'),
                'slot': slot,
                'fan_unit': 'RPM',
                'fan_source': None,
                'fan_label': None,
                'vram_mb': None,
                'power_limit': None,
                'subsysven': hw.get('subsystem'),
                'driver_version': None,
                'monitored': False,
                'data': {d: None for d in self.data},
            })
        return extra

    def get_inventory(self) -> list:
        """Return every GPU, discrete first, with its classification.

        Each entry: ``vendor``, ``name``, ``display``, ``kind``,
        ``kind_label``, ``slot``, ``fan_unit``, ``vram_mb``, ``power_limit``,
        ``subsysven``, ``driver_version``, ``primary`` and ``data`` (the
        live values keyed by metric name, ``None`` when unsupported).
        """
        entries = self._build_inventory()
        primary = self.get_primary()
        primary_name = primary['name'] if primary else None
        for entry in entries:
            entry['primary'] = (primary_name is not None
                                and entry['name'] == primary_name)
        return entries

    def get_primary(self) -> dict | None:
        """Return the GPU that takes precedence: the first discrete one.

        Falls back to the first GPU present, and to ``None`` when the system
        has no usable display adapter.
        """
        inventory = self._build_inventory()
        if not inventory:
            return None
        # A discrete GPU with live readings wins; otherwise any discrete GPU.
        for want_monitored in (True, False):
            for entry in inventory:
                if entry['kind'] == 'discrete' and entry['monitored'] == want_monitored:
                    return entry
        return inventory[0]

    def get_csv_data(self) -> list:
        """get a list of current gpu data for csv log

        Returns:
            list: list of current gpu data
        """
        ret = []
        for vendor in self.vendors:
            for name in self.gpus[vendor]['names']:
                for data in self.data:
                    if self.gpus[vendor][name][data] is not None:
                        ret.append(round(self.gpus[vendor][name][data], 4))
        return ret

    def get_csv_headings(self) -> list:
        """Get the CSV headings for GPU data

        Returns:
            list: list of csv headings
        """
        headings = []
        for vendor in self.vendors:
            for name in self.gpus[vendor]['names']:
                kind_label = KIND_LABELS.get(self.kind.get((vendor, name)), 'GPU')
                for data in self.data:
                    if self.gpus[vendor][name][data] is None:
                        continue
                    heading = f"{vendor} GPU {name} ({kind_label}) {data}"
                    if data == 'fan_speed':
                        # The unit differs per adapter, so spell it out.
                        source = self.fan_sources.get((vendor, name))
                        heading += (f" [{self.fan_units.get((vendor, name), 'RPM')}"
                                    f"{', system' if source == 'acpi' else ''}]")
                    headings.append(heading)
        return headings

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return self.lines

    def is_empty(self) -> bool:
        """is there a supported GPU?

        Returns:
            bool: True if no supported GPU present
        """
        if self.vendors:
            return False
        return True
