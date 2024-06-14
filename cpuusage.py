"""
CPU usage data
"""
from psutil import cpu_percent, cpu_count
from stressmon.hwsensors import HWSensorBase
from stressmon.cpuinfo import CPUInfo


class CPUUsage(HWSensorBase):
    """Class to collect CPU usage info."""

    headings = ['Core', 'Current(%)', 'Min(%)', 'Max(%)', 'Mean(%)']

    def __init__(self) -> None:
        self.iteration = 1
        self.cpuinfo = CPUInfo()
        self.cpucount = cpu_count(logical=True) + 1
        self.corecount = cpu_count(logical=True)
        self.p_cores = None
        if self.cpuinfo.has_intel_pe_cores():
            self.p_cores = self.cpuinfo.get_p_cores()
        self.labels = []
        mod = 0
        for core in range(self.cpucount):
            if core == 0:
                self.labels.append("CPU")
                mod = 1
                continue
            pe_str = ""
            if self.cpuinfo.has_intel_pe_cores():
                pe_str = "E "
                if (core - mod) < self.p_cores:
                    pe_str = "P "
            self.labels.append(f"{pe_str}Core {core-mod}")
        if self.cpuinfo.has_intel_pe_cores():
            self.labels.insert(1, 'E Cores')
            self.labels.insert(1, 'P Cores')
        self.usage = dict.fromkeys(self.labels, 0)
        self.mmm = dict.fromkeys(['min', 'max', 'mean'])
        self.mmm['min'] = dict.fromkeys(self.labels, 9999)
        self.mmm['max'] = dict.fromkeys(self.labels, 0)
        self.mmm['mean'] = dict.fromkeys(self.labels, 0)
        self._iter = None

    def __iter__(self):
        """Make class an iterator."""
        self._iter = iter(self.labels)
        return self

    def __next__(self) -> list:
        return [next(self._iter)]

    def update(self) -> None:
        """Update CPU usage."""
        main_cpu_usage = [cpu_percent()]
        per_cpu_usage = cpu_percent(percpu=True)
        p_core_usage = []
        e_core_usage = []
        if self.cpuinfo.has_intel_pe_cores():
            p_core_usage = [sum(per_cpu_usage[0:self.p_cores]) / self.p_cores]
            e_core_usage = [sum(per_cpu_usage[self.p_cores:]) / (self.corecount - self.p_cores)]
        usage = main_cpu_usage + p_core_usage + e_core_usage + per_cpu_usage
        self.usage = dict(zip(self.labels, usage))
        lmin = [min(cur_min, ele)
                for cur_min, ele in zip(self.mmm['min'].values(), usage)]
        lmax = [max(cur_max, ele)
                for cur_max, ele in zip(self.mmm['max'].values(), usage)]
        mean_values = zip(self.mmm['mean'].values(), usage)
        mean = [cur_mean + (ele - cur_mean) /
                self.iteration for cur_mean, ele in mean_values]
        self.mmm['min'] = dict(zip(self.labels, lmin))
        self.mmm['max'] = dict(zip(self.labels, lmax))
        self.mmm['mean'] = dict(zip(self.labels, mean))
        self.iteration += 1

    def get_section(self, _) -> str:
        """Get section"""
        return f"CPU: {self.get_model()}"

    def get_subsection(self, _) -> str | None:
        """Get subsection"""
        return None

    def get_model(self) -> str:
        """Get CPU model name"""
        return self.cpuinfo.get_model()

    def get_label(self, params: list) -> str | None:
        """Get label for current core"""
        if len(params) != 1:
            return None
        return params[0]

    def get_current(self, params: list) -> int | None:
        """Get current CPU usage for index."""
        if len(params) != 1:
            return None
        return round(self.usage[params[0]])

    def get_min(self, params: list) -> int | None:
        """Get minimum cpu usage for index."""
        if len(params) != 1:
            return None
        return round(self.mmm['min'][params[0]])

    def get_max(self, params: list) -> int | None:
        """Get maximum cpu usage for index."""
        if len(params) != 1:
            return None
        return round(self.mmm['max'][params[0]])

    def get_mean(self, params: list) -> int | None:
        """Get mean cpu usage for index rounded to nearest integer."""
        if len(params) != 1:
            return None
        return round(self.mmm['mean'][params[0]])

    def get_csv_data(self) -> list:
        """Return list of current usage

        Args:
            package (bool, optional): Include cpu package clock speed? Defaults to False.

        Returns:
            list: list of current CPU clock speeds
        """
        return [round(x, 4) for x in self.usage.values()]

    def get_csv_headings(self) -> list:
        """Generate Headings list for CSV file of current values

        Args:
            package (bool): Include CPU Package usage data?

        Returns:
            list: List of CSV heading names
        """
        return self.labels

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return len(self.usage)

    def get_win_columns(self) -> int:
        """return the number of columns needed for this data's curses window
        """
        return 50

    def is_empty(self) -> bool:
        """always returns false
        """
        return False
