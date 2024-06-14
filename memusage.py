"""MemUsage module
"""

from copy import deepcopy
from subprocess import run, PIPE
from psutil import virtual_memory, swap_memory
from stressmon.hwsensors import HWSensorBase

class MemUsage(HWSensorBase):
    """MemUsage class
    """

    headings = ['Memory', 'Current', 'Min', 'Max', 'Mean']

    def __init__(self):
        self.mem_iter = None
        self.current_mem = None
        self.data_iter = None
        self.iteration = 1
        self.mem = {'Mem': {'Total': 0, 'Available': 0, 'Used': 0, 'Percent': 0.0},
                    'Swap': {'Total': 0, 'Free': 0, 'Used': 0, 'Percent': 0.0}}
        self.mmm = dict.fromkeys(['min', 'max', 'mean'])
        self.mmm['min'] = deepcopy(self.mem)
        self.mmm['max'] = deepcopy(self.mem)
        self.mmm['mean'] = deepcopy(self.mem)
        for mem in self.mmm['min']:
            for data in self.mmm['min'][mem]:
                self.mmm['min'][mem][data] = 999999999999
        command = "dmidecode --type 17 | grep 'Part Number' | awk '{ print $3 }'"
        result = run([command],
                     shell=True,
                     check=True,
                     stdout=PIPE,
                     stderr=PIPE).stdout.decode("utf-8").split("\n")
        self.mem_skus = [x for x in result if x and x != 'Not' and x != 'Unknown']

    def __iter__(self):
        # Create an iterator for the memory data
        self.mem_iter = iter(self.mem.items())
        # Initialize the current memory item and an iterator for its keys (data)
        self.current_mem = next(self.mem_iter, None)
        self.data_iter = iter(self.current_mem[1]) if self.current_mem else iter([])
        return self

    def __next__(self):
        while self.current_mem:
            for data_item in self.data_iter:
                return [self.current_mem[0], data_item]

            # If we've exhausted data for the current memory item, move to the next one
            self.current_mem = next(self.mem_iter, None)
            self.data_iter = iter(self.current_mem[1]) if self.current_mem else iter([])

        # If we've exhausted all memory items, raise StopIteration
        raise StopIteration
    
    def get_mem_skus(self) -> str | None:
        if not self.mem_skus:
            return None
        return self.mem_skus

    def get_label(self, params: list) -> str | None:
        """Get label"""
        if len(params) != 2:
            return None
        return params[1]

    def update(self) -> None:
        """Update mem data
        """
        mem = virtual_memory()
        swap = swap_memory()
        self.mem = {'Mem':
                    {'Total': mem.total,
                     'Available': mem.available,
                     'Used': mem.used,
                     'Percent': mem.percent},
                    'Swap':
                    {'Total': swap.total,
                     'Free': swap.free,
                     'Used': swap.used,
                     'Percent': swap.percent}}
        for mem in self.mmm['min'].keys():
            for data in self.mmm['min'][mem].keys():
                self.mmm['min'][mem][data] = min(
                    self.mmm['min'][mem][data], self.mem[mem][data])
                self.mmm['max'][mem][data] = max(
                    self.mmm['max'][mem][data], self.mem[mem][data])
                self.mmm['mean'][mem][data] = self.mmm['mean'][mem][data] + \
                    (self.mem[mem][data] - self.mmm['mean'][mem][data]) / self.iteration
        self.iteration += 1

    def get_headings(self) -> list:
        """Get list of headings"""
        return self.headings

    def get_section(self, _) -> str | None:
        """Get section"""
        return "Memory Usage"

    def get_subsection(self, _) -> str | None:
        """Get section"""
        return None

    def get_current(self, params: list) -> int | None:
        """Get current memory data for index
        """
        if len(params) != 2:
            return None
        return round(self.mem[params[0]][params[1]])

    def get_min(self, params: list) -> int | None:
        """get minimum memory data for index
        """
        if len(params) != 2:
            return None
        return round(self.mmm['min'][params[0]][params[1]])

    def get_max(self, params: list) -> int | None:
        """get maximum memory data for index
        """
        if len(params) != 2:
            return None
        return round(self.mmm['max'][params[0]][params[1]])

    def get_mean(self, params: list) -> int | None:
        """get mean memory data for index rounded to nearest integer
        """
        if len(params) != 2:
            return None
        return round(self.mmm['mean'][params[0]][params[1]])

    def get_csv_data(self) -> list:
        """Return list of current mem data

        Returns:
            list: list of current mem data
        """
        ret = []
        for mem in list(self.mem.keys()):
            for data in list(self.mem[mem].keys()):
                ret.append(self.mem[mem][data])
        return ret

    def get_csv_headings(self) -> list:
        """Generate Headings list for CSV file of current values

        Returns:
            list: List of CSV heading names
        """
        headings = []
        for mem in list(self.mem.keys()):
            for data in list(self.mem[mem].keys()):
                headings.append(f"{mem} {data}")
        return headings

    # def get_win_lines(self) -> int:
    #    """return number of lines needed for this data's curses window
    #    """
    #    raise NotImplementedError

    # def get_win_columns(self) -> int:
    #    """return the number of columns needed for this data's curses window
    #    """
    #    raise NotImplementedError

    # def get_win_heading(self, params: list) -> str:
    #    """return a heading for this data's curses window
    #    """
    #    raise NotImplementedError

    # def get_win_sensor(self, params: list) -> str:
    #    """return a label for this data's curses window
    #    """
    #    raise Not ImplementedError

    def is_empty(self) -> bool:
        """Is the sensor empty?
        """
        return False
