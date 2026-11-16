"""Memory DIMM temperature sensor using psutil spd5118 data."""

import psutil
from stressmon.hwsensors import HWSensorBase


class MemTemp(HWSensorBase):
    """Memory DIMM temperature sensor class."""

    headings = ['DIMM', 'Current(C)', 'Min(C)', 'Max(C)', 'Mean(C)']

    def __init__(self):
        self.iteration = 1
        self.temps = {}
        self.mmm = {}
        self.labels = []
        self._init_sensors()

    def _init_sensors(self):
        spd = psutil.sensors_temperatures().get('spd5118', [])
        for i, entry in enumerate(spd):
            label = entry.label or f"DIMM {i}"
            self.labels.append(label)
            self.temps[label] = entry.current
            self.mmm[label] = [9999, 0, 0]

    def __iter__(self):
        self._iter = iter(self.labels)
        return self

    def __next__(self):
        return [next(self._iter)]

    def update(self):
        spd = psutil.sensors_temperatures().get('spd5118', [])
        for i, entry in enumerate(spd):
            label = entry.label or f"DIMM {i}"
            temp = entry.current
            if temp is None:
                # The DIMM sensor answered nothing this round (busy, or still
                # initialising).  min()/max() on None raised, which stopped
                # this sensor for the rest of the run.
                continue
            self.temps[label] = temp
            if label not in self.mmm:
                self.mmm[label] = [temp, temp, temp]
            else:
                self.mmm[label][0] = min(self.mmm[label][0], temp)
                self.mmm[label][1] = max(self.mmm[label][1], temp)
                mean = self.mmm[label][2]
                self.mmm[label][2] = mean + (temp - mean) / self.iteration
        self.iteration += 1

    def get_label(self, params):
        if len(params) != 1:
            return None
        return params[0]

    def get_section(self, _):
        return "Memory Temperatures"

    def get_subsection(self, _):
        return None

    def get_current(self, params):
        if len(params) != 1:
            return None
        temp = self.temps.get(params[0])
        return round(temp) if temp is not None else None

    def get_min(self, params):
        if len(params) != 1:
            return None
        entry = self.mmm.get(params[0], [None, None, None])
        return round(entry[0]) if entry[0] is not None else None

    def get_max(self, params):
        if len(params) != 1:
            return None
        entry = self.mmm.get(params[0], [None, None, None])
        return round(entry[1]) if entry[1] is not None else None

    def get_mean(self, params):
        if len(params) != 1:
            return None
        entry = self.mmm.get(params[0], [None, None, None])
        return round(entry[2]) if entry[2] is not None else None

    def get_csv_data(self):
        return [round(t, 4) for t in self.temps.values()]

    def get_csv_headings(self):
        return self.labels[:]

    def get_win_lines(self):
        return len(self.labels)

    def is_empty(self):
        return len(self.labels) == 0
