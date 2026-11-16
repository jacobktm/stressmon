"""Test doubles for stressmon sensors.

No test in this package touches real hardware: everything runs on these
objects, so the suite passes on a machine with no GPU, no smartctl and no
permission on the RAPL files.
"""

from stressmon.hwsensors import HWSensorBase


class FakeSensor(HWSensorBase):
    """A deterministic sensor with the full stressmon API.

    *rows* are the parameter tuples the real sensors iterate, ``(group...,
    label)``.  Each row contributes one value per metric, numbered from
    *base* so a test can point at a specific number in a CSV or summary.
    """

    metrics = ("current", "min", "max", "mean")

    def __init__(self, rows, base=10, mismatch=0, extra=0):
        self.rows = [tuple(row) for row in rows]
        self.mmm = {'min': {}, 'max': {}, 'mean': {}}
        self.iteration = 1
        self.mismatch = mismatch        # deliberate heading/data drift, see below
        self.extra = extra
        self.vals = {}
        n = base
        for row in self.rows:
            for metric in self.metrics:
                n += 1
                self.vals[(row, metric)] = n / 2.0

    def update(self):
        pass

    def __iter__(self):
        return iter(self.rows)

    def is_empty(self):
        return not self.rows

    def get_label(self, params):
        return params[-1]

    def get_section(self, params):
        return params[0]

    def get_subsection(self, params):
        return params[1] if len(params) > 1 else ""

    def _value(self, params, metric):
        return self.vals[(tuple(params), metric)]

    def get_current(self, params):
        return self._value(params, "current")

    def get_min(self, params):
        return self._value(params, "min")

    def get_max(self, params):
        return self._value(params, "max")

    def get_mean(self, params):
        return self._value(params, "mean")

    def get_csv_headings(self):
        return [f"{'>'.join(str(part) for part in row)} {metric}"
                for row in self.rows for metric in self.metrics]

    def get_csv_data(self):
        """Values for every row; *mismatch*/*extra* break the contract on purpose."""
        values = [self._value(row, metric)
                  for row in self.rows for metric in self.metrics]
        if self.mismatch:
            values = values[self.mismatch:]
        if self.extra:
            values = values + [0.0] * self.extra
        return values


class PowerSensor(FakeSensor):
    """Stands in for CPUWatts, which has a section name of its own."""

    def get_section(self, params):
        return "RAPL"


class ModelSensor(FakeSensor):
    """Stands in for CPUFreq: the summary asks it for the CPU model."""

    def __init__(self, rows, model="Fake CPU Model", **kwargs):
        super().__init__(rows, **kwargs)
        self.model = model

    def get_model(self):
        return self.model


class SkuSensor(FakeSensor):
    """Stands in for MemUsage, which reports DIMM part numbers."""

    def __init__(self, rows, skus=("S7-A1", "S7-B2"), **kwargs):
        super().__init__(rows, **kwargs)
        self.skus = skus

    def get_mem_skus(self):
        return self.skus


class GpuSensor(FakeSensor):
    """Stands in for GPUData (rows are ``(vendor, name, metric)``)."""

    def __init__(self, rows, driver_version="550.54.14", subvendor="System76", **kwargs):
        super().__init__(rows, **kwargs)
        self.driver_version = driver_version
        self.subvendor = subvendor

    def get_driver_version(self):
        return self.driver_version

    def get_subven(self, vendor, name):
        return self.subvendor if vendor == "nvidia" else ""


class DriveSensor(FakeSensor):
    """Stands in for DriveTemp (rows are ``(device, label)``)."""

    def get_model(self, drive):
        return f"model of {drive}"
