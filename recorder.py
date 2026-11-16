"""Shared recording helpers for the monitors.

``test.py`` (curses), ``test_gui.py`` (tkinter) and the webui all record the
same sensors to the same kind of CSV.  Column order comes from the caller, so
each monitor keeps the layout its downstream tooling expects, but the way
headings and data line up, the CSV writing and the summary text are written
once here.

The contract that matters: a sensor contributes ``get_csv_headings()`` names
and ``get_csv_data()`` values, and the two must be the same length.  When they
are not, every column after that sensor is shifted by the difference, which
silently pairs a temperature with a fan reading in the file that gets shipped
back as a result.  :class:`Recorder` keeps the row rectangular and says so.
"""

import logging
from csv import writer
from subprocess import run, PIPE, CalledProcessError

log = logging.getLogger(__name__)


def get_model_name() -> str:
    """The system model name from dmidecode, or "Unknown" if it can't be read.

    Needs sudo dmidecode.  A failure here must not take a monitor down at
    startup: burn-in runs unattended, and the model name is a line of a header.
    """
    try:
        model = run(["sudo dmidecode -t 1 | grep Version | awk '{print $2}'"],
                    shell=True,
                    check=True,
                    stdout=PIPE).stdout.decode('utf-8').strip()
    except (CalledProcessError, OSError):
        return "Unknown"
    return model or "Unknown"


def format_line(items, column_widths, justifications):
    """Format one line of a fixed-width table.

    :param items: List of strings in the line.
    :param column_widths: List of widths for each column.
    :param justifications: List of justification characters ('<', '>', '^').
    :return: Formatted line, with a trailing newline.
    """
    line_format = "".join("{:" + just + str(width) + "}"
                          for just, width in zip(justifications, column_widths)) + "\n"
    return line_format.format(*items)


class Recorder:
    """Builds CSV headings and data rows for an ordered list of sensors.

    *sensors* is in column order.  *prefix* names the columns the caller
    supplies itself, normally ``["Runtime"]`` or ``["RunID", "Runtime"]``.
    """

    def __init__(self, sensors, prefix=("Runtime",)):
        self.sensors = list(sensors)
        self.prefix = list(prefix)

    def active_sensors(self):
        """Sensors that contribute columns (those with csv support)."""
        return [sensor for sensor in self.sensors
                if sensor is not None and hasattr(sensor, "get_csv_headings")]

    def headings(self):
        """Header row: the prefix columns, then every sensor's headings."""
        row = list(self.prefix)
        for sensor in self.active_sensors():
            row.extend(sensor.get_csv_headings())
        return row

    def data(self):
        """Sensor values only, aligned with ``headings()[len(prefix):]``.

        A sensor whose data and heading counts disagree is padded with empty
        strings, or trimmed, so the columns after it stay in place.
        """
        row = []
        for sensor in self.active_sensors():
            names = sensor.get_csv_headings()
            values = list(sensor.get_csv_data())
            if len(values) != len(names):
                log.warning("Sensor %s wrote %d values for %d headings; realigned",
                            type(sensor).__name__, len(values), len(names))
                values = (values + [""] * len(names))[:len(names)]
            row.extend(values)
        return row

    def row(self, *prefix_values):
        """A complete data row: the caller's prefix values, then the sensors."""
        return list(prefix_values) + self.data()

    def width(self):
        """Number of columns in a row written by this recorder."""
        return len(self.headings())


def write_header(csv_fn, headings):
    """Write the heading row, replacing any existing file contents."""
    with open(file=csv_fn, mode='w', encoding='utf-8', newline='') as outfile:
        writer(outfile).writerow(headings)


def write_row(csv_fn, row, mode='a'):
    """Append one data row to the CSV file."""
    with open(file=csv_fn, mode=mode, encoding='utf-8', newline='') as outfile:
        writer(outfile).writerow(row)


def build_summary(mhz, ctemps, watts, fans, gpus, drives, usage, mem,
                  model_name, start_time, run_time):
    """Build the min/max/mean summary the burn-in monitors write alongside the CSV.

    Every sensor argument is a stressmon sensor object; sections are skipped
    when the sensor has nothing to report.
    """
    data = f"Summary:\nModel: {model_name}\nStart Time: {start_time}\n"
    data += f"Runtime: {run_time}\nCPU: {mhz.get_model()}\n"
    data += "Memory SKUs:\n"
    for sku in (mem.get_mem_skus() or []):
        data += f"DIMM: {sku}\n"
    mem_type = ''
    column_widths = [15, 20, 20, 20]
    justifications = ['<', '>', '>', '>']
    headers = []
    for params in mem:
        if mem_type != params[0]:
            mem_type = params[0]
            headers = [mem_type, "Min", "Max", "Mean"]
            data += format_line(headers, column_widths, justifications)
        data_row = [mem.get_label(params), mem.get_min(params),
                    mem.get_max(params), mem.get_mean(params)]
        data += format_line(data_row, column_widths, justifications)
    column_widths = [15, 15, 15, 15]
    justifications = ['<', '>', '>', '>']
    headers = ["Core", "Min %:Mhz", "Max %:Mhz", "Mean %:Mhz"]
    data += format_line(headers, column_widths, justifications)
    for mhz_params, usage_params in zip(mhz, usage):
        data_row = [mhz.get_label(mhz_params),
                    f"{usage.get_min(usage_params):>4}:{mhz.get_min(mhz_params):>5}",
                    f"{usage.get_max(usage_params):>4}:{mhz.get_max(mhz_params):>5}",
                    f"{usage.get_mean(usage_params):>4}:{mhz.get_mean(mhz_params):>5}"]
        data += format_line(data_row, column_widths, justifications)
    data += "\n"
    if not ctemps.is_empty():
        column_widths = [15, 10, 10, 10]
        justifications = ['<', '>', '>', '>']
        headers = ["Core", "Min C", "Max C", "Mean C"]
        data += format_line(headers, column_widths, justifications)
        for params in ctemps:
            data_row = [ctemps.get_label(params), ctemps.get_min(params),
                        ctemps.get_max(params), ctemps.get_mean(params)]
            data += format_line(data_row, column_widths, justifications)
        data += "\n"
    if not watts.is_empty():
        column_widths = [10, 10, 10, 10]
        justifications = ['<', '>', '>', '>']
        headers = ["CPU", "Min W", "Max W", "Mean W"]
        data += format_line(headers, column_widths, justifications)
        for params in watts:
            data_row = [watts.get_label(params), watts.get_min(params),
                        watts.get_max(params), watts.get_mean(params)]
            data += format_line(data_row, column_widths, justifications)
        data += "\n"
    if not fans.is_empty():
        data += "Fans\n"
        driver = ''
        column_widths = [15, 15, 15, 15, 15]
        justifications = ['<', '>', '>', '>', '>']
        for params in fans:
            if driver != params[0]:
                driver = params[0]
                data += f"{driver}:\n"
                headers = ["Fan", "Current(RPM)", "Min(RPM)", "Max(RPM)", "Mean(RPM)"]
                data += format_line(headers, column_widths, justifications)
            data_row = [fans.get_label(params), fans.get_current(params), fans.get_min(params),
                        fans.get_max(params), fans.get_mean(params)]
            data += format_line(data_row, column_widths, justifications)
        data += "\n"
    if not gpus.is_empty():
        data += "GPUs\n"
        vendor = ''
        name = ''
        column_widths = [15, 15, 15, 15, 15]
        justifications = ['<', '>', '>', '>', '>']
        for params in gpus:
            driver_version = ""
            if vendor != params[0]:
                vendor = params[0]
                if vendor == 'nvidia':
                    driver_version = " - " + gpus.get_driver_version()
                data += f"{vendor}{driver_version}:\n"
            if name != params[1]:
                name = params[1]
                data += f"GPU: {name}\n"
                if gpus.get_subven(vendor, name):
                    data += f"SubSystem: {gpus.get_subven(vendor, name)}\n"
                headers = ["Data", "Current", "Min", "Max", "Mean"]
                data += format_line(headers, column_widths, justifications)
            if gpus.get_current(params) is not None:
                data_row = [gpus.get_label(params), gpus.get_current(params), gpus.get_min(params),
                            gpus.get_max(params), gpus.get_mean(params)]
                data += format_line(data_row, column_widths, justifications)
        data += "\n"
    if not drives.is_empty():
        data += "Drives\n"
        drive = ''
        column_widths = [15, 15, 15, 15, 15]
        justifications = ['<', '>', '>', '>', '>']
        headers = ["Data", "Current", "Min", "Max", "Mean"]
        for params in drives:
            if drive != params[0]:
                drive = params[0]
                data += f"Device: {drive}\nDrive Model: {drives.get_model(drive)}\n"
                data += format_line(headers, column_widths, justifications)
            if drives.get_current(params) is not None:
                data_row = [drives.get_label(params), drives.get_current(params),
                            drives.get_min(params), drives.get_max(params),
                            drives.get_mean(params)]
                data += format_line(data_row, column_widths, justifications)
        data += "\n"
    return data


def write_summary(summary_fn, mhz, ctemps, watts, fans, gpus, drives, usage, mem,
                  model_name, start_time, run_time):
    """Build the summary text and write it to *summary_fn*."""
    data = build_summary(mhz, ctemps, watts, fans, gpus, drives, usage, mem,
                         model_name, start_time, run_time)
    with open(file=summary_fn, mode='w', encoding='utf-8') as outfile:
        outfile.write(data)


def write_column_summary(summary_fn, csv_fn, headers, rows, fn_time):
    """Write a per-column min/max/mean summary for a recorded CSV.

    *rows* holds the data rows (no header); *headers* names each column.
    Non-numeric cells are skipped, which is how the empty placeholders left
    by an absent sensor stay out of the statistics.
    """
    ncols = len(headers)
    mins = [float('inf')] * ncols
    maxs = [float('-inf')] * ncols
    sums = [0.0] * ncols
    count = len(rows)
    for row in rows:
        for i, val in enumerate(row):
            if val is not None and val != "":
                v = float(val)
                mins[i] = min(mins[i], v)
                maxs[i] = max(maxs[i], v)
                sums[i] += v
    with open(file=summary_fn, mode='w', encoding='utf-8') as outfile:
        outfile.write(f"Log file: {csv_fn}\n")
        outfile.write(f"Date: {fn_time}\n\n")
        outfile.write(f"{'Sensor':<35} {'Min':>12} {'Max':>12} {'Mean':>12}\n")
        outfile.write("-" * 75 + "\n")
        for i, h in enumerate(headers):
            mn = f"{mins[i]:>10.2f}" if mins[i] != float('inf') else " " * 12
            mx = f"{maxs[i]:>10.2f}" if maxs[i] != float('-inf') else " " * 12
            mean = f"{sums[i]/count:>10.2f}" if count > 0 else " " * 12
            outfile.write(f"{h:<35} {mn:>12} {mx:>12} {mean:>12}\n")
