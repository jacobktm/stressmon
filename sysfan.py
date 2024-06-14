"""Hardware monitor module for fan sensor data
"""

from copy import deepcopy
from psutil import sensors_fans
from stressmon.hwsensors import HWSensorBase


class SysFan(HWSensorBase):
    """System Fans sensor class
    """

    headings = ['Fans', 'Current(RPM)', 'Min(RPM)', 'Max(RPM)', 'Mean(RPM)']

    def __init__(self) -> None:
        self.iteration = 1
        self.drivers = [driver for driver in sensors_fans().keys()
                        if driver != 'amdgpu']
        self.fans = {}
        self.mmm = {}
        self.lines = len(self.drivers) * 2
        if self.drivers:
            self.fans = dict.fromkeys(self.drivers)
            for driver in self.drivers:
                fans = list(sensors_fans()[driver])
                fans = [fan[0] for fan in fans]
                for i, fan in enumerate(fans):
                    if fan == '':
                        fans[i] = driver
                    self.lines += 1
                self.fans[driver] = dict.fromkeys(fans)
            self.lines += 1
            self.mmm = deepcopy(self.fans)
            for driver in self.drivers:
                fans = list(self.mmm[driver].keys())
                for fan in fans:
                    self.mmm[driver][fan] = [9999, 0, 0]
        self.driver_iter = None
        self.current_driver = None
        self.current_fans = None
        self.fan_iter = None

    def __iter__(self):
        # Create an iterator for drivers
        self.driver_iter = iter(self.fans.items())

        # Get the first driver and its associated fans
        self.current_driver, self.current_fans = next(self.driver_iter, (None, None))

        # Create an iterator for the fans of the current driver
        self.fan_iter = iter(self.current_fans) if self.current_driver else iter([])

        return self

    def __next__(self) -> list:
        # As long as there are drivers left to process
        while self.current_driver:
            # Try to get the next fan for the current driver
            for fan in self.fan_iter:
                return [self.current_driver, fan]

            # If we've processed all fans for the current driver, get the next driver
            self.current_driver, self.current_fans = next(self.driver_iter, (None, None))

            # Reset the fan iterator for the new driver
            self.fan_iter = iter(self.current_fans) if self.current_driver else iter([])

        # If we've exhausted all drivers and fans, raise StopIteration
        raise StopIteration

    def get_drivers(self) -> list:
        """Get list of supported fan drivers

        Returns:
            list: list of supported fan drivers
        """
        return self.drivers

    def get_fan_names(self, driver: str) -> list:
        """Get list of fans in supported driver

        Args:
            driver (str): driver name

        Returns:
            list: list of fans in supported driver
        """
        return list(self.fans.get(driver, {}).keys())

    def update(self) -> None:
        """Update fan speeds
        """
        if self.drivers:
            current = sensors_fans()
            for driver in self.drivers:
                fans = list(current[driver])
                for fan in fans:
                    fan = list(fan)
                    if fan[0] == '':
                        fan[0] = driver
                    self.fans[driver][fan[0]] = fan[1]
                    self.mmm[driver][fan[0]][0] = min(
                        [self.mmm[driver][fan[0]][0], fan[1]])
                    self.mmm[driver][fan[0]][1] = max(
                        [self.mmm[driver][fan[0]][1], fan[1]])
                    mean = self.mmm[driver][fan[0]][2]
                    self.mmm[driver][fan[0]][2] = mean + \
                        (fan[1] - mean) / self.iteration
        self.iteration += 1

    def get_label(self, params: list) -> str | None:
        """Get label for current fan"""
        if len(params) != 2:
            return None
        return params[1]

    def get_section(self, params: list) -> str | None:
        """Get section"""
        if len(params) != 2:
            return None
        return f"{params[0]}"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_current(self, params: list) -> int | None:
        """Get the current fan speed for fans[driver][fan]

        Args:
            driver (str): supported driver name
            fan (str): fan name

        Returns:
            int: current fan speed
        """
        if len(params) != 2:
            return None
        return self.fans.get(params[0], {}).get(params[1], None)

    def get_min(self, params: list) -> int | None:
        """Get the minimum fan speed for fans[driver][fan]

        Args:
            driver (str): supported driver name
            fan (str): fan name

        Returns:
            int: minimum fan speed
        """
        if len(params) != 2:
            return None
        return self.mmm.get(params[0], {}).get(params[1], (None, None, None))[0]

    def get_max(self, params: list) -> int | None:
        """Get the maximum fan speed for fans[driver][fan]

        Args:
            driver (str): supported driver name
            fan (str): fan name

        Returns:
            int: maximum fan speed
        """
        if len(params) != 2:
            return None
        return self.mmm.get(params[0], {}).get(params[1], (None, None, None))[1]

    def get_mean(self, params: list) -> int | None:
        """Get the mean fan speed for fans[driver][fan]

        Args:
            driver (str): supported driver name
            fan (str): fan name

        Returns:
            int: mean fan speed
        """
        if len(params) != 2:
            return None
        ret = self.mmm.get(params[0], {}).get(params[1], (None, None, None))[2]
        if ret is None:
            return ret
        return round(ret)

    def get_csv_data(self) -> list:
        """get fan speeds as a list

        Returns:
            list: list of fan speeds
        """
        ret = []
        if self.drivers:
            for driver in self.drivers:
                fans = self.fans[driver].keys()
                for fan in fans:
                    ret.append(self.fans[driver][fan])
        return ret

    def get_csv_headings(self) -> list:
        """Get list of headings

        Returns:
            list: list of headings
        """
        headings = []
        if self.drivers:
            for driver in self.drivers:
                fans = list(self.fans[driver].keys())
                for fan in fans:
                    headings.append(f"{driver} {fan}")
        return headings

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return self.lines

    def is_empty(self) -> bool:
        """Are there fan drivers?

        Returns:
            bool: True if there are fan drivers
        """
        if self.drivers:
            return False
        return True
