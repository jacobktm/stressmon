"""Drive temp sensor monitor class
"""

from copy import deepcopy
from pySMART import DeviceList
from stressmon.hwsensors import HWSensorBase


class DriveTemp(HWSensorBase):
    """NVMe Temperature class
    """

    sensors = ['Composite', 'Sensor 1', 'Sensor 2']
    headings = ['Data', 'Current(C)', 'Min(C)', 'Max(C)', 'Mean(C)']

    def __init__(self) -> None:
        self.iteration = 1
        device_list = DeviceList()
        self.drive_count = len(device_list.devices)
        self.drives = {}
        self.lines = self.drive_count * 2
        if self.drive_count > 0:
            for device in device_list.devices:
                self.drives[device.name] = {}
                self.drives[device.name]['Model'] = device.model
                self.drives[device.name]['Composite'] = None
                self.lines += 1
                for sensor in device.temperatures.keys():
                    self.drives[device.name][f"Sensor {sensor}"] = None
                    self.lines += 1
            self.lines += 1
        self.mmm = deepcopy(self.drives)
        for drive in self.mmm.keys():
            for sensor in self.mmm[drive].keys():
                self.mmm[drive][sensor] = [9999, 0, 0]

    def __iter__(self):
        for drive, sensors in self.drives.items():
            for sensor_name in [name for name in sensors.keys() if name != 'Model']:
                yield [drive, sensor_name]

    def __next__(self):
        return next(self.__iter__())

    def update(self) -> None:
        """update NVMe temps
        """
        if self.drive_count > 0:
            for device in DeviceList().devices:
                temp = device.temperature
                self.drives[device.name]['Composite'] = temp
                minimum = min([self.mmm[device.name]['Composite'][0], temp])
                maximum = max([self.mmm[device.name]['Composite'][1], temp])
                mean = self.mmm[device.name]['Composite'][2]
                mean = mean + (temp - mean) / self.iteration
                self.mmm[device.name]['Composite'] = [minimum, maximum, mean]
                for sensor in device.temperatures.keys():
                    temp = device.temperatures[sensor]
                    self.drives[device.name][f"Sensor {sensor}"] = temp
                    minimum = min(
                        [self.mmm[device.name][f"Sensor {sensor}"][0], temp])
                    maximum = max(
                        [self.mmm[device.name][f"Sensor {sensor}"][1], temp])
                    mean = self.mmm[device.name][f"Sensor {sensor}"][2]
                    mean = mean + (temp - mean) / self.iteration
                    self.mmm[device.name][f"Sensor {sensor}"] = [
                        minimum, maximum, mean]
        self.iteration += 1

    def get_label(self, params: list) -> str | None:
        """Get label for current sensor"""
        if len(params) != 2:
            return None
        return params[1]

    def get_section(self, params: list) -> str | None:
        """Get section"""
        if len(params) != 2:
            return None
        return f"{params[0]} - {self.get_model(params[0])}"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_sensors(self) -> list:
        """return list of sensors

        Returns:
            list: list of sensors
        """
        return self.sensors

    def get_drive_names(self) -> list:
        """get list of drive names

        Returns:
            list: list of drive names
        """
        return list(self.drives.keys())

    def get_model(self, drive: str) -> str:
        """get drive model name

        Args:
            drive (str): drive name

        Returns:
            str: drive model name
        """
        drive = self.drives.get(drive, {})
        return drive.get('Model', '')

    def get_current(self, params: list) -> int | None:
        """Get current NVMe temperature for sensor for drive
        """
        if len(params) != 2:
            return None
        return self.drives.get(params[0], {}).get(params[1], None)

    def get_min(self, params: list) -> int | None:
        """get minimum NVMe temperature for sensor for drive
        """
        if len(params) != 2:
            return None
        return self.mmm.get(params[0], {}).get(params[1], [None, None, None])[0]

    def get_max(self, params: list) -> int | None:
        """get maximum NVMe temperature for sensor for drive
        """
        if len(params) != 2:
            return None
        return self.mmm.get(params[0], {}).get(params[1], [None, None, None])[1]

    def get_mean(self, params: list) -> int | None:
        """get mean NVMe temperature for sensor for drive
        """
        if len(params) != 2:
            return None
        ret = self.mmm.get(params[0], {}).get(params[1], [None, None, None])[2]
        if ret is None:
            return ret
        return round(ret)

    def get_csv_data(self) -> list:
        """Return list of current NVMe temps

        Returns:
            list: list of current NVMe clock speeds
        """
        return [
            round(value, 4)
            for _, drive_info in self.drives.items()
            for key, value in drive_info.items()
            if key != 'Model' and value is not None
        ]

    def get_csv_headings(self) -> list:
        """Generate Headings list for CSV file of current values

        Returns:
            list: List of CSV heading names
        """
        if self.drive_count == 0:
            return []
        return [
            f"{drive} {sensor}"
            for drive, drive_info in self.drives.items()
            for sensor in drive_info.keys()
            if sensor != 'Model'
        ]

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return self.lines

    def is_empty(self) -> bool:
        """is drive temp data empty?
        """
        ret = True
        if self.drive_count > 0:
            ret = False
        return ret
