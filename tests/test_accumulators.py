"""Min/max/mean accumulator reset, the shape every sensor's history comes in."""

import unittest

from stressmon.hwsensors import HWSensorBase
from stressmon.tests.fakes import FakeSensor


class TestResetAccumulators(unittest.TestCase):
    """reset_accumulators() has to handle every layout the sensors use."""

    def sensor(self, mmm, iteration=40):
        sensor = FakeSensor([("a",)])
        sensor.mmm = mmm
        sensor.iteration = iteration
        return sensor

    def test_flat_history(self):
        """CPUFreq, CPUUsage, MemUsage: {'min'|'max'|'mean': {label: value}}"""
        sensor = self.sensor({'min': {'cpu0': 400.0},
                              'max': {'cpu0': 4800.0},
                              'mean': {'cpu0': 2100.0}})
        sensor.reset_accumulators()
        self.assertEqual(sensor.mmm['min']['cpu0'], HWSensorBase.MIN_SENTINEL)
        self.assertEqual(sensor.mmm['max']['cpu0'], 0)
        self.assertEqual(sensor.mmm['mean']['cpu0'], 0)

    def test_nested_history(self):
        """CPUTemp, MemUsage: {'min': {group: {label: value}}}"""
        sensor = self.sensor({'min': {'pkg': {'core0': 41.0, 'core1': 43.0}},
                              'max': {'pkg': {'core0': 88.0, 'core1': 90.0}},
                              'mean': {'pkg': {'core0': 62.0, 'core1': 64.0}}})
        sensor.reset_accumulators()
        self.assertEqual(sensor.mmm['min']['pkg'],
                         {'core0': HWSensorBase.MIN_SENTINEL,
                          'core1': HWSensorBase.MIN_SENTINEL})
        self.assertEqual(sensor.mmm['max']['pkg']['core1'], 0)

    def test_leaf_list_history(self):
        """SysFan, DriveTemp, MemTemp, GPUData: {entity: {metric: [min,max,mean]}}"""
        sensor = self.sensor({'fan1': {'input': [400, 6000, 2100],
                                       'label': ["not", "a", "triple"]}})
        sensor.reset_accumulators()
        self.assertEqual(sensor.mmm['fan1']['input'],
                         [HWSensorBase.MIN_SENTINEL, 0, 0])
        self.assertEqual(sensor.mmm['fan1']['label'], ["not", "a", "triple"])

    def test_mean_divisor_restarts(self):
        sensor = self.sensor({'min': {}, 'max': {}, 'mean': {}})
        sensor.reset_accumulators()
        self.assertEqual(sensor.iteration, 1)

    def test_live_readings_are_left_alone(self):
        sensor = FakeSensor([("a",)])
        before = sensor.get_current(("a",))
        sensor.reset_accumulators()
        self.assertEqual(sensor.get_current(("a",)), before)


if __name__ == "__main__":
    unittest.main()
