"""
CPU clock speed data
"""
from psutil import cpu_freq, cpu_count
from stressmon.hwsensors import HWSensorBase
from stressmon.cpuinfo import CPUInfo


class CPUFreq(HWSensorBase):
    """Class to collect CPU frequency info."""

    headings = ['Core', 'Current(MHz)', 'Min(MHz)', 'Max(MHz)', 'Mean(MHz)']

    def __init__(self) -> None:
        self.iteration = 1
        self.cpuinfo = CPUInfo()
        self.p_cores = None
        if self.cpuinfo.has_intel_pe_cores():
            self.p_cores = self.cpuinfo.get_p_cores()
        if cpu_freq()[0] > 100:
            self.multiplier = 1
        else:
            self.multiplier = 1000
        self.cpucount = cpu_count(logical=True) + 1
        self.corecount = cpu_count(logical=True)
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
        self.mhz = dict.fromkeys(self.labels, 0)
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
        """Update CPU frequency."""
        main_cpu_freq = [cpu_freq()[0] * self.multiplier]
        per_cpu_freqs = [(x[0] * self.multiplier)
                         for x in cpu_freq(percpu=True)]
        p_core_freq = []
        e_core_freq = []
        if self.cpuinfo.has_intel_pe_cores():
            p_core_freq = [sum(per_cpu_freqs[0:self.p_cores]) / self.p_cores]
            e_core_freq = [sum(per_cpu_freqs[self.p_cores:]) / (self.corecount - self.p_cores)]
        mhz = main_cpu_freq + p_core_freq + e_core_freq + per_cpu_freqs
        self.mhz = dict(zip(self.labels, mhz))
        lmin = [min(cur_min, ele)
                for cur_min, ele in zip(self.mmm['min'].values(), mhz)]
        lmax = [max(cur_max, ele)
                for cur_max, ele in zip(self.mmm['max'].values(), mhz)]
        mean_values = zip(self.mmm['mean'].values(), mhz)
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
        """Get current clock speed for index."""
        if len(params) != 1:
            return None
        return round(self.mhz[params[0]])

    def get_min(self, params: list) -> int | None:
        """Get minimum cpu clock speed for index."""
        if len(params) != 1:
            return None
        return round(self.mmm['min'][params[0]])

    def get_max(self, params: list) -> int | None:
        """Get maximum cpu clock speed for index."""
        if len(params) != 1:
            return None
        return round(self.mmm['max'][params[0]])

    def get_mean(self, params: list) -> int | None:
        """Get mean cpu clock speed for index rounded to nearest integer."""
        if len(params) != 1:
            return None
        return round(self.mmm['mean'][params[0]])

    def get_csv_data(self) -> list:
        """Return list of current clock speed

        Args:
            package (bool, optional): Include cpu package clock speed? Defaults to False.

        Returns:
            list: list of current CPU clock speeds
        """
        return [round(x, 4) for x in self.mhz.values()]

    def get_csv_headings(self) -> list:
        """Generate Headings list for CSV file of current values

        Args:
            package (bool): Include CPU Package clock speed data?

        Returns:
            list: List of CSV heading names
        """
        return self.labels

    def get_win_lines(self) -> int:
        """return number of lines needed for this data's curses window
        """
        return len(self.mhz)

    def get_win_columns(self) -> int:
        """return the number of columns needed for this data's curses window
        """
        return 50

    def is_empty(self) -> bool:
        """always returns false
        """
        return False
