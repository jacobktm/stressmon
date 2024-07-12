"""CPU Watt monitor
"""

from time import time_ns
from os.path import exists
from stressmon.hwsensors import HWSensorBase


class CPUWatts(HWSensorBase):
    """Logging CPU power usage
    """

    headings = ["CPU", "Current(W)", "Min(W)", "Max(W)", "Mean(W)"]

    def __init__(self):
        self.cpu_count = 1
        self.watts = {}
        self.file_time = {}
        self.cpu_joules = {}
        self.mmm = {'min': {}, 'max': {}, 'mean': {}}
        self.iteration = 1
        self.labels = []
        self._iter = None
        if not exists('/sys/class/powercap/intel-rapl:0/energy_uj'):
            self.cpu_count = 0
            return
        if exists('/sys/class/powercap/intel-rapl:1/energy_uj'):
            self.cpu_count = 2
        for i in range(self.cpu_count):
            index = f"CPU{i}"
            self.labels.append(index)
            energy_uj = f"/sys/class/powercap/intel-rapl:{i}/energy_uj"
            with open(energy_uj, 'r', encoding='UTF-8') as joule_file:
                self.cpu_joules[index] = joule_file.read()
                self.file_time[index] = time_ns()
            self.cpu_joules[index] = int(self.cpu_joules[index])
            self.watts[index] = 0
            self.mmm['min'][index] = 9999
            self.mmm['max'][index] = 0
            self.mmm['mean'][index] = 0

    def __iter__(self):
        """Make class an iterator."""
        self._iter = iter(self.labels)
        return self

    def __next__(self) -> list:
        return [next(self._iter)]

    def update(self):
        """Calculate CPU Watts
        """
        for i in range(self.cpu_count):
            index = f"CPU{i}"
            start_joule = self.cpu_joules[index]
            start_time = self.file_time[index]
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
        return "CPU Watts"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_current(self, params: list) -> int | None:
        """Get current sensor data
        """
        if len(params) != 1:
            return None
        return round(self.watts[params[0]])

    def get_min(self, params: list) -> int | None:
        """Get minimum value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['min'][params[0]])

    def get_max(self, params: list) -> int | None:
        """Get maximum value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['max'][params[0]])

    def get_mean(self, params: list) -> int | None:
        """Get average value for sensor data
        """
        if len(params) != 1:
            return None
        return round(self.mmm['mean'][params[0]])

    def get_csv_headings(self) -> list:
        """Return headings for csv file for sensor
        """
        ret = []
        for cpu in self.labels:
            ret.append(f"{cpu}(Watts)")
        return ret

    def get_csv_data(self) -> list:
        """Return list of sensor data for sensor
        """
        return [round(x, 4) for x in self.watts.values()]

    def is_empty(self) -> bool:
        """Is the sensor empty?
        """
        if not self.watts:
            return True
        return False

    def get_count(self):
        return len(self.watts)

