"""The RAPL spike filter: real load steps must be reported, wrap-around junk must not."""

import unittest

from stressmon.cpuwatts import (_SPIKE_ACCEPT_AFTER, _SPIKE_RATIO, _SPIKE_WATTS,
                                CPUWatts)


def _filter():
    """A CPUWatts with no sysfs attached: only the filter is under test."""
    sensor = CPUWatts.__new__(CPUWatts)
    sensor.watts = {}
    sensor.rejections = {}
    return sensor


class TestPlausible(unittest.TestCase):
    """CPUWatts._plausible decides which readings reach the CSV."""

    def test_zero_and_negative_are_dropped(self):
        """The energy counter wraps; a raced read goes negative."""
        sensor = _filter()
        self.assertFalse(sensor._plausible('Package', 0))
        self.assertFalse(sensor._plausible('Package', -60000))

    def test_first_reading_is_taken(self):
        sensor = _filter()
        self.assertTrue(sensor._plausible('Package', 5.0))

    def test_small_load_step_is_accepted_at_once(self):
        """10 W to 30 W is inside the band, so it is believed immediately."""
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        self.assertTrue(sensor._plausible('Package', 30.0))

    def test_large_load_step_is_believed_after_a_few_updates(self):
        """The regression: this compared against the running mean.

        An idle baseline of 10 W settled the mean near 10, so a genuine 250 W
        load sat above the threshold on every single round and the reported
        watts stayed frozen at idle for the rest of the run.  Comparing with
        the last accepted reading instead costs a big step
        _SPIKE_ACCEPT_AFTER updates and then believes it.
        """
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        verdicts = [sensor._plausible('Package', 250.0)
                    for _ in range(_SPIKE_ACCEPT_AFTER)]
        self.assertEqual(verdicts, [False] * (_SPIKE_ACCEPT_AFTER - 1) + [True])

    def test_wrap_around_jump_is_dropped(self):
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        self.assertFalse(sensor._plausible('Package', 5000.0))

    def test_a_sustained_level_becomes_real(self):
        """Still reporting it for _SPIKE_ACCEPT_AFTER rounds: believe it."""
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        verdicts = [sensor._plausible('Package', 900.0)
                    for _ in range(_SPIKE_ACCEPT_AFTER)]
        self.assertEqual(verdicts[:-1], [False] * (_SPIKE_ACCEPT_AFTER - 1))
        self.assertTrue(verdicts[-1])

    def test_sustained_counter_resets_after_a_good_read(self):
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        sensor._plausible('Package', 900.0)          # rejected once
        self.assertTrue(sensor._plausible('Package', 12.0))
        sensor.watts['Package'] = 12.0
        # two rejections in a row is not enough; the counter restarts at the
        # accepted reading, so this is rejected again
        self.assertFalse(sensor._plausible('Package', 900.0))

    def test_small_step_above_the_absolute_band_is_accepted(self):
        """A 6 W machine stepping to 20 W is a real change, not a spike."""
        sensor = _filter()
        sensor.watts['Package'] = 6.0
        self.assertTrue(sensor._plausible('Package', 20.0))

    def test_thresholds_are_the_documented_ones(self):
        sensor = _filter()
        sensor.watts['Package'] = 10.0
        limit = max(10.0 * _SPIKE_RATIO, 10.0 + _SPIKE_WATTS)
        self.assertTrue(sensor._plausible('Package', limit))
        self.assertFalse(sensor._plausible('Package', limit + 0.01))


if __name__ == "__main__":
    unittest.main()
