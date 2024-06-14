"""Logging CPU Core temperatures"""

from copy import deepcopy
from re import findall
from psutil import sensors_temperatures
from stressmon.hwsensors import HWSensorBase


def extract_number(s):
    """extract numbers
    """
    numbers = findall(r'\d+', s)
    num = int(numbers[0]) if numbers else -1
    is_priority = 'Tctl' in s or 'Package id' in s
    return (not is_priority, num)


class CPUTemp(HWSensorBase):
    """CPU Temperature sensor class
    """
    sensors = ['coretemp', 'k10temp']
    headings = ['Core', 'Current(C)', 'Min(C)', 'Max(C)', 'Mean(C)']

    def __init__(self) -> None:
        self.iteration = 1
        self.sensor = None
        self.temps = {}
        sensors_temps = sensors_temperatures()
        for sensor in self.sensors:
            if sensor in sensors_temps.keys():
                self.sensor = sensor
                cpu_num = 0
                cpu_sensor = ''
                cpu_core = ''
                for temp_sensor in sensors_temps[sensor]:
                    cpu_core = temp_sensor[0]
                    if cpu_core == 'Tctl' or cpu_core == f"Package id {cpu_num}":
                        cpu_sensor = cpu_core
                        if cpu_core == 'Tctl':
                            cpu_sensor = f"Tctl{cpu_num}"
                            cpu_core = cpu_sensor
                        self.temps[cpu_sensor] = {}
                        cpu_num += 1
                    self.temps[cpu_sensor][cpu_core] = 0
                # Sort the inner dictionaries after the loop
                for cpu_sensor, sensor_temps in self.temps.items():
                    sorted_keys = sorted(sensor_temps.keys(), key=extract_number)
                    self.temps[cpu_sensor] = {k: sensor_temps[k] for k in sorted_keys}
                self.mmm = dict.fromkeys(['min', 'max', 'mean'])
                self.mmm['min'] = deepcopy(self.temps)
                self.mmm['max'] = deepcopy(self.temps)
                self.mmm['mean'] = deepcopy(self.temps)
                for cpu in self.mmm['min']:
                    for temp in self.mmm['min'][cpu]:
                        self.mmm['min'][cpu][temp] = 9999
        self.cpu_iter = None
        self.current_cpu = None
        self.core_iter = None

    def __iter__(self):
        self.cpu_iter = iter(self.temps.items())
        self.current_cpu = next(self.cpu_iter, None)
        if self.current_cpu:
            self.core_iter = iter(self.current_cpu[1])
        else:
            self.core_iter = iter([])
        return self

    def __next__(self) -> list:
        while self.current_cpu:
            for core in self.core_iter:
                return [self.current_cpu[0], core]

            # Move to next CPU
            self.current_cpu = next(self.cpu_iter, None)
            if self.current_cpu:
                self.core_iter = iter(self.current_cpu[1])
            else:
                self.core_iter = iter([])

        # No more CPUs
        raise StopIteration

    def update(self) -> None:
        """update CPU temps
        """

        sensors_temps = sensors_temperatures()
        cpu_num = 0
        cpu_sensor = ''
        cpu_core = ''
        for temp_sensor in sensors_temps[self.sensor]:
            cpu_core = temp_sensor[0]
            if cpu_core == 'Tctl' or cpu_core == f"Package id {cpu_num}":
                cpu_sensor = cpu_core
                if temp_sensor[0] == 'Tctl':
                    cpu_sensor = f"Tctl{cpu_num}"
                    cpu_core = cpu_sensor
                cpu_num += 1
            self.temps[cpu_sensor][cpu_core] = temp_sensor[1]
        for cpu in self.mmm['min']:
            for temp in self.mmm['min'][cpu]:
                self.mmm['min'][cpu][temp] = min(
                    self.mmm['min'][cpu][temp], self.temps[cpu][temp])
                self.mmm['max'][cpu][temp] = max(
                    self.mmm['max'][cpu][temp], self.temps[cpu][temp])
                self.mmm['mean'][cpu][temp] = self.mmm['mean'][cpu][temp] + \
                    (self.temps[cpu][temp] - self.mmm['mean']
                     [cpu][temp]) / self.iteration
        self.iteration += 1

    def get_label(self, params: list) -> str | None:
        """Get label for current core"""
        if len(params) != 2:
            return None
        return params[1]

    def get_section(self, params: list) -> str | None:
        """Get section"""
        return "CPU Core Temperatures"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_current(self, params: list) -> int | None:
        """Get current temperature for index
        """
        if len(params) != 2:
            return None
        return round(self.temps[params[0]][params[1]])

    def get_min(self, params: list) -> int | None:
        """get minimum cpu temperature for index
        """
        if len(params) != 2:
            return None
        return round(self.mmm['min'][params[0]][params[1]])

    def get_max(self, params: list) -> int | None:
        """get maximum cpu temperature for index
        """
        if len(params) != 2:
            return None
        return round(self.mmm['max'][params[0]][params[1]])

    def get_mean(self, params: list) -> int | None:
        """get mean cpu temperature for index rounded to nearest integer
        """
        if len(params) != 2:
            return None
        return round(self.mmm['mean'][params[0]][params[1]])

    def get_csv_data(self) -> list:
        """Return list of current cpu temps

        Returns:
            list: list of current CPU temps
        """
        ret = []
        for cpu in list(self.temps.keys()):
            for core in list(self.temps[cpu].keys()):
                ret.append(self.temps[cpu][core])
        return ret

    def get_csv_headings(self) -> list:
        """Generate Headings list for CSV file of current values

        Returns:
            list: List of CSV heading names
        """
        headings = []
        for cpu in list(self.temps.keys()):
            for core in list(self.temps[cpu].keys()):
                headings.append(f"{cpu} {core}")
        return headings

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return len(self.temps)

    def is_empty(self) -> bool:
        """Is cpu temp class empty?
        """
        ret = False
        if not self.temps:
            ret = True
        return ret
