"""Module for GPU Data
"""

from copy import deepcopy
from re import findall
from subprocess import run, PIPE, CalledProcessError
from psutil import sensors_fans
from pyamdgpuinfo import detect_gpus, get_gpu
from pynvml import nvmlInit, NVMLError, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,   \
    nvmlDeviceGetName, nvmlDeviceGetPowerManagementLimit, nvmlShutdown,    \
    nvmlDeviceGetFanSpeed, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU, \
    nvmlDeviceGetPowerUsage, nvmlDeviceGetUtilizationRates,                \
    nvmlSystemGetDriverVersion, nvmlDeviceGetClock, NVML_CLOCK_GRAPHICS,   \
    NVML_CLOCK_ID_CURRENT, nvmlDeviceGetMemoryInfo
from stressmon.hwsensors import HWSensorBase


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

    def __init__(self) -> None:
        self.vendor_iter = None
        self.name_iter = None
        self.data_iter = None
        self.current_vendor = None
        self.current_name = None
        self.vendors = []
        self.gpus = {}
        self.iteration = 1
        self.data = ['temp', 'clock', 'fan_speed', 'power', 'memory', 'utilization']
        handles = []
        gpuinfos = []
        self.lines = 1
        nvidia_gpu_count = 0
        amd_gpu_count = detect_gpus()
        try:
            nvmlInit()
            self.vendors.append('nvidia')
            nvidia_gpu_count = nvmlDeviceGetCount()

            command = r'lspci -vvnn | grep -A 3 "\[0300\]" | grep -A 3 NVIDIA'
            nvidia_gpu_data = run([command], shell=True, check=True, stdout=PIPE, stderr=PIPE)
            nvidia_gpu_data = nvidia_gpu_data.stdout
            nvidia_gpu_data = nvidia_gpu_data.decode('utf-8').split("\n--\n")
            pattern = r"\[(\w{4}:\w{4})\]"
            nvidia_subvens = []
            for nvidia_gpu in nvidia_gpu_data:
                result = findall(pattern=pattern, string=nvidia_gpu)
                if len(result) > 1:
                    nvidia_subvens.append(result[1].split(":")[0])
                else:
                    nvidia_subvens.append(None)

            self.lines += 1
        except NVMLError:
            pass
        if amd_gpu_count > 0:
            command = r'lspci -vvnn | grep -A 3 "\[0300\]" | grep -A 3 AMD'
            amd_gpu_data = run([command], shell=True, check=True, stdout=PIPE, stderr=PIPE)
            amd_gpu_data = amd_gpu_data.stdout
            amd_gpu_data = amd_gpu_data.decode('utf-8').split("\n--\n")
            pattern = r"\[(\w{4}:\w{4})\]"
            amd_devs = []
            amd_subvens = []
            for amd_gpu in amd_gpu_data:
                result = findall(pattern=pattern, string=amd_gpu)
                amd_devs.append(result[0].split(":")[1])
                if len(result) > 1:
                    amd_subvens.append(result[1].split(":")[0])
                else:
                    amd_subvens.append(None)

            self.vendors.append('amdgpu')
            self.lines += 1
        if self.vendors:
            self.gpus = dict.fromkeys(self.vendors)
            if 'nvidia' in self.vendors:
                self.gpus['nvidia'] = {}
                self.gpus['nvidia']['handles'] = []
                self.gpus['nvidia']['names'] = []
                self.lines += nvidia_gpu_count * 2
                for i in range(nvidia_gpu_count):
                    handle = nvmlDeviceGetHandleByIndex(i)
                    name = f"{nvmlDeviceGetName(handle)}-{i}"
                    try:
                        power_limit = nvmlDeviceGetPowerManagementLimit(
                            handle) / 1000
                    except NVMLError:
                        power_limit = None
                    handles.append(handle)
                    subven = str(nvidia_subvens[i])
                    if subven:
                        command = f"cat venids | grep -i \"{subven},\""
                        try:
                            output = run([command],
                                         shell=True,
                                         check=True,
                                         stdout=PIPE,
                                         stderr=PIPE).stdout.decode('utf-8')
                            subven = output[5:]
                        except CalledProcessError:
                            pass

                    mem_limit = round((nvmlDeviceGetMemoryInfo(handle).total / 1024 / 1024), 2)
                    self.gpus['nvidia']['names'].append(name)
                    self.gpus['nvidia'][name] = {'temp': None, 'clock': None, 'fan_speed': None,
                                                 'power': None, 'power_limit': power_limit,
                                                 'memory': None, 'mem_limit': mem_limit,
                                                 'utilization': None, 'subsysven': subven}
                    self.lines += 6
            if 'amdgpu' in self.vendors:
                self.gpus['amdgpu'] = {}
                self.gpus['amdgpu']['names'] = []
                self.gpus['amdgpu']['gpuinfos'] = []
                self.lines += amd_gpu_count * 2
                for i in range(amd_gpu_count):
                    gpuinfo = get_gpu(i)
                    name = f"Device_{str(amd_devs[i])}-{i}"
                    if gpuinfo.name:
                        name = f"{gpuinfo.name}-{i}"
                    else:
                        command = f"cat amddevids | grep -i \"{amd_devs[i]},\""
                        try:
                            output = run([command],
                                         shell=True,
                                         check=True,
                                         stdout=PIPE,
                                         stderr=PIPE).stdout.decode('utf-8')
                            output = output.replace("\n", "")
                            name = f"{output[5:]}-{i}"
                        except CalledProcessError:
                            pass

                    subven = str(amd_subvens[i])
                    if subven:
                        command = f"cat venids | grep -i \"{subven},\""
                        try:
                            output = run([command],
                                         shell=True,
                                         check=True,
                                         stdout=PIPE,
                                         stderr=PIPE).stdout.decode('utf-8')
                            subven = output[5:]
                        except CalledProcessError:
                            pass

                    mem_limit = round((gpuinfo.memory_info['vram_size'] / 1024 / 1024), 2)
                    gpuinfos.append(gpuinfo)
                    self.gpus['amdgpu']['names'].append(name)
                    self.gpus['amdgpu'][name] = {'temp': None, 'clock': None, 'fan_speed': None,
                                                 'power': None, 'power_limit': None,
                                                 'memory': None, 'mem_limit': mem_limit,
                                                 'utilization': None, 'subsysven': subven}
                    self.lines += 5
            self.mmm = deepcopy(self.gpus)
            if handles:
                self.gpus['nvidia']['handles'] = [handle for handle in handles]
            if gpuinfos:
                self.gpus['amdgpu']['gpuinfos'] = [
                    gpuinfo for gpuinfo in gpuinfos]
            for vendor in self.vendors:
                for name in self.mmm[vendor]['names']:
                    for data in self.data:
                        self.mmm[vendor][name][data] = [999999, 0, 0]

    def __del__(self) -> None:
        if 'nvidia' in self.vendors:
            nvmlShutdown()

    def __iter__(self):
        self.vendor_iter = iter(self.vendors)
        self._next_vendor()
        return self

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
                gpu_index = gpu_data['names'].index(gpu_name)

                if vendor == 'nvidia':
                    handle = self.gpus[vendor]['handles'][gpu_index]
                    fan_speed = None
                    try:
                        fan_speed = nvmlDeviceGetFanSpeed(handle)
                        if self.iteration == 1:
                            self.lines += 1
                    except NVMLError:
                        pass

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
                    gpuinfo = self.gpus[vendor]['gpuinfos'][gpu_index]
                    fan_speed = None
                    fans = sensors_fans()
                    if 'amdgpu' in fans.keys():
                        try:
                            fan_speed = fans['amdgpu'][gpuinfo.gpu_id][1]
                            if self.iteration == 1:
                                self.lines += 1
                        except IndexError:
                            pass

                    self.gpus[vendor][gpu_name]['temp'] = gpuinfo.query_temperature()
                    self.gpus[vendor][gpu_name]['fan_speed'] = fan_speed
                    self.gpus[vendor][gpu_name]['power'] = gpuinfo.query_power()
                    self.gpus[vendor][gpu_name]['memory'] = round(
                        (gpuinfo.query_vram_usage() / 1024 / 1024), 2)
                    self.gpus[vendor][gpu_name]['utilization'] = gpuinfo.query_load(
                    ) * 100

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
                for data in self.data:
                    if self.gpus[vendor][name][data] is not None:
                        headings.append(f"{vendor} {name} {data}")
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
