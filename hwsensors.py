"""Hardware monitoring base class for hardware sensors
"""

from abc import ABC, abstractmethod


class HWSensorBase(ABC):
    """Base class for system hardware monitoring sensors
    """

    headings = []

    # Value written back over a minimum when the accumulators are cleared.
    # It is deliberately the same value the web UI uses so both reset paths
    # leave a sensor's Min column displaying as empty rather than a number.
    MIN_SENTINEL = 999999999

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

    def reset_accumulators(self) -> None:
        """Clear this sensor's min/max/mean history and restart the mean.

        Handles every accumulator layout the sensors use:

          {'min'|'max'|'mean': {label: value, ...}}        flat
          {'min'|'max'|'mean': {group: {label: value}}}    nested
          {entity: {metric: [min, max, mean], ...}}        per-leaf lists

        Live readings are left alone; only the recorded history is dropped
        and ``iteration`` (the mean's divisor) restarts at 1.
        """
        mmm = getattr(self, 'mmm', None)
        if mmm is not None:
            self._reset_mmm(mmm)
        if hasattr(self, 'iteration'):
            self.iteration = 1

    @classmethod
    def _reset_mmm(cls, node: dict, key: str = None) -> None:
        """Walk an accumulator dict; ``key`` is 'min'/'max'/'mean' once known."""
        if not isinstance(node, dict):
            return
        if key in ('min', 'max', 'mean'):
            target = cls.MIN_SENTINEL if key == 'min' else 0
            for sub_key, value in node.items():
                if isinstance(value, dict):
                    cls._reset_mmm(value, key)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    node[sub_key] = target
            return
        for sub_key, value in node.items():
            if (isinstance(value, list) and len(value) == 3
                    and all(isinstance(v, (int, float)) for v in value)):
                value[0] = cls.MIN_SENTINEL
                value[1] = 0
                value[2] = 0
            elif isinstance(value, dict):
                cls._reset_mmm(value, sub_key)

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
