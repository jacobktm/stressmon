"""The update pool: a sensor that starts failing has to be visible somewhere."""

import unittest

from stressmon.updatepool import UpdatePool


class TestUpdatePool(unittest.TestCase):
    """Sensor updates run in threads, so their exceptions need reporting."""

    def test_failing_update_is_reported(self):
        """A future's exception is otherwise dropped and the readings just go stale."""
        pool = UpdatePool()

        def boom():
            raise RuntimeError("NVML device disappeared")
        pool.add_executor('gpu_data', boom)
        with self.assertLogs("stressmon.updatepool", level="ERROR"):
            pool.do_updates()
        self.assertEqual(pool.get_errors(),
                         {'gpu_data': 'RuntimeError: NVML device disappeared'})

    def test_recovering_clears_the_error(self):
        pool = UpdatePool()
        state = {'failing': True}

        def update():
            if state['failing']:
                raise OSError("sensor busy")
        pool.add_executor('cpu_temp', update)
        with self.assertLogs("stressmon.updatepool", level="ERROR"):
            pool.do_updates()
        self.assertIn('cpu_temp', pool.get_errors())
        state['failing'] = False
        pool.do_updates()
        self.assertEqual(pool.get_errors(), {})

    def test_the_same_failure_is_logged_once(self):
        """Overnight a failing sensor retries every cycle; the journal stays readable."""
        pool = UpdatePool()

        def boom():
            raise RuntimeError("smartctl went away")
        pool.add_executor('drive_temp', boom)
        with self.assertLogs("stressmon.updatepool", level="ERROR") as logs:
            for _ in range(5):
                pool.do_updates()
        errors = [line for line in logs.output if "drive_temp" in line]
        self.assertEqual(len(errors), 1)

    def test_empty_pool_does_not_raise(self):
        """A machine with no sensors detected at all still starts a pool."""
        pool = UpdatePool()
        pool.do_updates()
        self.assertEqual(pool.get_errors(), {})

    def test_one_failure_does_not_stop_the_others(self):
        pool = UpdatePool()
        seen = []
        pool.add_executor('bad', lambda: 1 / 0)
        pool.add_executor('good', lambda: seen.append(1))
        pool.do_updates()
        self.assertEqual(seen, [1])
        self.assertIn('bad', pool.get_errors())


if __name__ == "__main__":
    unittest.main()
