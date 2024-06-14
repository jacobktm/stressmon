"""Hardware monitoring base class for hardware sensors
"""

from abc import ABC, abstractmethod


class HWSensorBase(ABC):
    """Base class for system hardware monitoring sensors
    """

    headings = []

    @abstractmethod
    def get_label(self, params: list) -> str | None:
        """Get label"""
        raise NotImplementedError

    @abstractmethod
    def update(self) -> None:
        """Update hardware sensor
        """
        raise NotImplementedError

    def get_headings(self) -> list:
        """Get list of headings"""
        return self.headings

    @abstractmethod
    def get_section(self, params: list) -> str | None:
        """Get section"""
        raise NotImplementedError

    @abstractmethod
    def get_subsection(self, params: list) -> str | None:
        """Get section"""
        raise NotImplementedError

    @abstractmethod
    def get_current(self, params: list) -> int | None:
        """Get current sensor data
        """
        raise NotImplementedError

    @abstractmethod
    def get_min(self, params: list) -> int | None:
        """Get minimum value for sensor data
        """
        raise NotImplementedError

    @abstractmethod
    def get_max(self, params: list) -> int | None:
        """Get maximum value for sensor data
        """
        raise NotImplementedError

    @abstractmethod
    def get_mean(self, params: list) -> int | None:
        """Get average value for sensor data
        """
        raise NotImplementedError

    @abstractmethod
    def get_csv_headings(self) -> list:
        """Return headings for csv file for sensor
        """
        raise NotImplementedError

    @abstractmethod
    def get_csv_data(self) -> list:
        """Return list of sensor data for sensor
        """
        raise NotImplementedError

    # @abstractmethod
    # def get_win_lines(self) -> int:
    #    """return number of lines needed for this data's curses window
    #    """
    #    raise NotImplementedError

    # @abstractmethod
    # def get_win_columns(self) -> int:
    #    """return the number of columns needed for this data's curses window
    #    """
    #    raise NotImplementedError

    # @abstractmethod
    # def get_win_heading(self, params: list) -> str:
    #    """return a heading for this data's curses window
    #    """
    #    raise NotImplementedError

    # @abstractmethod
    # def get_win_sensor(self, params: list) -> str:
    #    """return a label for this data's curses window
    #    """
    #    raise Not ImplementedError

    @abstractmethod
    def is_empty(self) -> bool:
        """Is the sensor empty?
        """
        return False
