"""CPU Watt monitor
"""

from time import time_ns
from os.path import exists
from stressmon.hwsensors import HWSensorBase


_SHORT_NAMES = {
    "package-0": "Package",
    "psys": "Platform",
    "core": "Cores",
    "uncore": "Uncore",
}


def _domain_name(domain_index):
    """Read the RAPL domain name from sysfs, falling back to 'CPU<N>'."""
    name_file = f"/sys/class/powercap/intel-rapl:{domain_index}/name"
    try:
        with open(name_file, encoding='UTF-8') as f:
            return f.read().strip()
    except Exception:
        return f"CPU{domain_index}"


class CPUWatts(HWSensorBase):
    """Logging CPU power usage
    """

    headings = ["CPU", "Current(W)", "Min(W)", "Max(W)", "Mean(W)"]

    def __init__(self):
        self.cpu_count = 0
        self.watts = {}
        self.file_time = {}
        self.cpu_joules = {}
        self.mmm = {'min': {}, 'max': {}, 'mean': {}}
        self.iteration = 1
        self.labels = []
        self._iter = None

        for i in range(2):
            energy_uj = f"/sys/class/powercap/intel-rapl:{i}/energy_uj"
            if not exists(energy_uj):
                continue
            raw = _domain_name(i)
            index = _SHORT_NAMES.get(raw, raw)
            self.labels.append(index)
            with open(energy_uj, 'r', encoding='UTF-8') as joule_file:
                self.cpu_joules[index] = joule_file.read()
                self.file_time[index] = time_ns()
            self.cpu_joules[index] = int(self.cpu_joules[index])
            self.watts[index] = 0
            self.mmm['min'][index] = 9999
            self.mmm['max'][index] = 0
            self.mmm['mean'][index] = 0
            self.cpu_count += 1

    def __iter__(self):
        """Make class an iterator."""
        self._iter = iter(self.labels)
        return self

    def __next__(self) -> list:
        return [next(self._iter)]

    def update(self):
        """Calculate CPU Watts
        """
        for index in self.labels:
            start_joule = self.cpu_joules[index]
            start_time = self.file_time[index]
            i = self.labels.index(index)
            energy_uj = f"/sys/class/powercap/intel-rapl:{i}/energy_uj"
            with open(energy_uj, 'r', encoding='UTF-8') as joule_file:
                self.cpu_joules[index] = joule_file.read()
                self.file_time[index] = time_ns()
            self.cpu_joules[index] = int(self.cpu_joules[index])
            joule_diff = self.cpu_joules[index] - start_joule
            duration = self.file_time[index] - start_time
            watts = joule_diff / (duration / 1000)
            if watts > 0 and (watts < (self.mmm['mean'][index] * 2.5) or self.mmm['mean'][index] == 0):
                self.watts[index] = watts
            self.mmm['min'][index] = min(
                self.mmm['min'][index], self.watts[index])
            self.mmm['max'][index] = max(
                self.mmm['max'][index], self.watts[index])
            self.mmm['mean'][index] = self.mmm['mean'][index] + \
                (self.watts[index] - self.mmm['mean'][index]) / self.iteration
        self.iteration += 1

    def get_label(self, params: list) -> str | None:
        """Get label for current core"""
        if len(params) != 1:
            return None
        return params[0]

    def get_section(self, _) -> str | None:
        """Get section"""
        return "CPU Power"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_current(self, params: list) -> int | None:
        """Get current sensor data
        """
        if len(params) != 1:
            return None
        return round(self.watts.get(params[0], 0))

    def get_min(self, params: list) -> int | None:
        """Get minimum value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['min'].get(params[0], 0))

    def get_max(self, params: list) -> int | None:
        """Get maximum value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['max'].get(params[0], 0))

    def get_mean(self, params: list) -> int | None:
        """Get average value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['mean'].get(params[0], 0))

    def get_csv_headings(self) -> list:
        """Return headings for csv file for sensor
        """
        return [f"{cpu}(Watts)" for cpu in self.labels]

    def get_csv_data(self) -> list:
        """Return list of sensor data for sensor
        """
        return [round(self.watts.get(cpu, 0), 4) for cpu in self.labels]

    def is_empty(self) -> bool:
        """Is the sensor empty?
        """
        if not self.watts:
            return True
        return False

    def get_count(self):
        return len(self.watts)

