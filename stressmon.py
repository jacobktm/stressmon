"""Stress utility monitoring class
"""

from psutil import process_iter

class StressMon:
    """Class to monitor and report info about stress utilities
    """
    stress_utilities = ['stress-ng', 'gpu_burn', 'glmark2', 'valley', 'Superposition', 'memtester']
