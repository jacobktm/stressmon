"""CPU info class
"""

from psutil import cpu_count
from cpuinfo import get_cpu_info


class CPUInfo:
    """Class to store CPU Info"""

    def __init__(self) -> None:
        self.model = get_cpu_info()['brand_raw']
        self.vendor = get_cpu_info()['vendor_id_raw']
        self.cores = cpu_count(logical=False)
        self.threads = cpu_count(logical=True)
        self.intel_pe_cores = False
        # I wish there was a better way...using math to detect P-cores and E-cores
        if self.cores != self.threads and self.cores > (self.threads / 2):
            self.intel_pe_cores = True
        self.p_cores = None
        self.p_threads = None
        if self.intel_pe_cores:
            self.p_cores = self.threads - self.cores
            self.p_threads = self.p_cores * 2

    def get_model(self) -> str:
        """get CPU model

        Returns:
            str: CPU model
        """
        return self.model

    def get_vendor(self) -> str:
        """get CPU vendor

        Returns:
            str: CPU vendor
        """
        return self.vendor

    def get_count(self, logical: bool = True) -> int:
        """return CPU core count

        Args:
            logical (bool, optional): return logical CPU cores?. Defaults to True.

        Returns:
            int: CPU core count
        """
        if logical:
            return self.threads
        return self.cores

    def has_intel_pe_cores(self) -> bool:
        """does this CPU have P/E cores?

        Returns:
            bool: True if CPU has Intel P/E Cores
        """
        return self.intel_pe_cores

    def get_p_cores(self, logical: bool = True) -> int | None:
        """get number of Intel Performance cores

        Args:
            logical (bool, optional): get logical intel performance cores?. Defaults to True.

        Returns:
            int | None: Number of P cores or None
        """
        if logical:
            return self.p_threads
        return self.p_cores
