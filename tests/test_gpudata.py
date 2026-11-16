"""GPU data: the guards that keep one bad adapter from ending the update pass."""

import unittest

from stressmon import gpudata
from stressmon.gpudata import NVMLError, GPUData, _amd, _nvml


def _stub_gpu():
    """A GPUData with two adapters and no drivers involved."""
    gpu = GPUData.__new__(GPUData)
    gpu.vendors = ['nvidia', 'intel']
    gpu.data = ['temp', 'clock', 'fan_speed', 'power', 'memory', 'utilization']
    gpu.kind = {('nvidia', 'GPU0'): 'discrete', ('intel', 'iGPU'): 'integrated'}
    gpu.fan_units = {('nvidia', 'GPU0'): '%', ('intel', 'iGPU'): 'RPM'}
    gpu.fan_sources = {('nvidia', 'GPU0'): 'driver', ('intel', 'iGPU'): 'acpi'}
    metrics = {'temp': 55.0, 'clock': 2100.0, 'fan_speed': 40.0, 'power': None,
               'memory': 1234.0, 'utilization': 10.0}
    gpu.gpus = {
        'nvidia': {'names': ['GPU0'], 'GPU0': dict(metrics)},
        'intel': {'names': ['iGPU'], 'iGPU': dict(metrics)},
    }
    return gpu


class TestNvmlAmdGuards(unittest.TestCase):
    """One adapter dropping off the bus must not stop the other sensors."""

    def test_nvml_error_becomes_none(self):
        def boom():
            raise NVMLError("uninitialized")
        self.assertIsNone(_nvml(boom))

    def test_nvml_passes_values_through(self):
        self.assertEqual(_nvml(lambda: 42), 42)

    def test_amd_error_becomes_none(self):
        def boom():
            raise RuntimeError("pyamdgpuinfo not initialised")
        self.assertIsNone(_amd(boom))


class TestNvmlLifecycle(unittest.TestCase):
    """NVML is one library per process, not one per GPUData."""

    def setUp(self):
        self.original_init = gpudata.nvmlInit
        self.original_shutdown = gpudata.nvmlShutdown
        self.original_users = gpudata._nvml_users
        self.addCleanup(self.restore)

    def restore(self):
        gpudata.nvmlInit = self.original_init
        gpudata.nvmlShutdown = self.original_shutdown
        gpudata._nvml_users = self.original_users

    def test_shutdown_waits_for_the_last_sensor(self):
        """The monitor re-creates empty sensors, so two can exist at once."""
        shutdowns = []
        gpudata.nvmlInit = lambda: None
        gpudata.nvmlShutdown = lambda: shutdowns.append(1)
        gpudata._nvml_users = 0
        self.assertTrue(gpudata._nvml_init())
        self.assertTrue(gpudata._nvml_init())
        gpudata._nvml_shutdown()
        self.assertEqual(shutdowns, [])
        gpudata._nvml_shutdown()
        self.assertEqual(shutdowns, [1])

    def test_init_failure_is_not_an_exception(self):
        def boom():
            raise NVMLError("driver not loaded")
        gpudata.nvmlInit = boom
        gpudata._nvml_users = 0
        self.assertFalse(gpudata._nvml_init())
        self.assertEqual(gpudata._nvml_users, 0)

    def test_shutdown_error_is_swallowed(self):
        def boom():
            raise NVMLError("uninitialized")
        gpudata.nvmlShutdown = boom
        gpudata._nvml_users = 0
        gpudata._nvml_shutdown()
        self.assertEqual(gpudata._nvml_users, 0)


class TestCsvContract(unittest.TestCase):
    """One field per heading, whatever the drivers reported."""

    def test_row_width_matches_headings(self):
        gpu = _stub_gpu()
        self.assertEqual(len(gpu.get_csv_data()), len(gpu.get_csv_headings()))

    def test_missing_reading_is_an_empty_field(self):
        """The Intel iGPU has no power source here; the column still exists."""
        gpu = _stub_gpu()
        headings = gpu.get_csv_headings()
        row = gpu.get_csv_data()
        power = [index for index, heading in enumerate(headings)
                 if heading.endswith(" power")]
        self.assertEqual(len(power), 2)
        for index in power:
            self.assertEqual(row[index], '')

    def test_fan_headings_name_their_unit(self):
        headings = _stub_gpu().get_csv_headings()
        self.assertTrue(any("fan_speed [%]" in heading for heading in headings))
        self.assertTrue(any("fan_speed [RPM, system]" in heading for heading in headings))

    def test_headings_name_the_adapter_kind(self):
        headings = _stub_gpu().get_csv_headings()
        self.assertTrue(any("(dGPU)" in heading for heading in headings))
        self.assertTrue(any("(iGPU)" in heading for heading in headings))


if __name__ == "__main__":
    unittest.main()
