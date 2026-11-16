"""The heading/data contract every recorded CSV depends on."""

import csv
import tempfile
import unittest
from subprocess import CalledProcessError

from stressmon import recorder
from stressmon.recorder import (Recorder, build_summary, format_line,
                                write_column_summary, write_header, write_row)
from stressmon.tests.fakes import (DriveSensor, FakeSensor, GpuSensor, ModelSensor,
                                   PowerSensor, SkuSensor)


class TempFileMixin(unittest.TestCase):
    """Shared temporary file handling."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return f"{self.tmp.name}/{name}"

    def read(self, fn):
        with open(fn, encoding='utf-8') as handle:
            return handle.read()


class TestRecorder(TempFileMixin):
    """Recorder keeps the heading row and the data rows the same shape."""

    def sensors(self):
        """One of each sensor, each with its own label so order is visible."""
        return [ModelSensor([("freq0",)]),
                FakeSensor([("temp0",)]),
                PowerSensor([("watt0",)]),
                FakeSensor([("coretemp", "fan0")]),
                GpuSensor([("nvidia", "GPU0", "temp"), ("nvidia", "GPU0", "power")]),
                DriveSensor([("/dev/nvme0", "Temperature")]),
                SkuSensor([("Mem", "Used")]),
                FakeSensor([("use0",)])]

    def test_row_matches_header_length(self):
        rec = Recorder(self.sensors())
        header = rec.headings()
        self.assertEqual(header[:1], ["Runtime"])
        self.assertEqual(len(rec.row(1.5)), len(header))

    def test_column_order_follows_the_sensor_list(self):
        """Each monitor's downstream tooling reads a fixed layout."""
        rec = Recorder(self.sensors())
        self.assertEqual([heading.split()[0] for heading in rec.headings()[1:]],
                         ["freq0", "freq0", "freq0", "freq0",
                          "temp0", "temp0", "temp0", "temp0",
                          "watt0", "watt0", "watt0", "watt0",
                          "coretemp>fan0", "coretemp>fan0", "coretemp>fan0", "coretemp>fan0",
                          "nvidia>GPU0>temp", "nvidia>GPU0>temp", "nvidia>GPU0>temp",
                          "nvidia>GPU0>temp",
                          "nvidia>GPU0>power", "nvidia>GPU0>power", "nvidia>GPU0>power",
                          "nvidia>GPU0>power",
                          "/dev/nvme0>Temperature", "/dev/nvme0>Temperature",
                          "/dev/nvme0>Temperature", "/dev/nvme0>Temperature",
                          "Mem>Used", "Mem>Used", "Mem>Used", "Mem>Used",
                          "use0", "use0", "use0", "use0"])
        flipped = Recorder(list(reversed(self.sensors())))
        self.assertEqual(flipped.headings()[1], "use0 current")

    def test_short_data_is_padded_not_shifted(self):
        """A sensor with fewer values than headings must not shift the rest."""
        broken = FakeSensor([("temp0",)], mismatch=2)
        rec = Recorder([broken, PowerSensor([("watt0",)])])
        header = rec.headings()
        row = rec.row(0.0)
        self.assertEqual(len(row), len(header))
        self.assertEqual(header[-1], "watt0 mean")
        self.assertEqual(row[-1], 7.0)
        self.assertEqual(row[3], "")          # the two values that were missing

    def test_extra_data_is_dropped(self):
        rec = Recorder([FakeSensor([("temp0",)], extra=2), PowerSensor([("watt0",)])])
        self.assertEqual(len(rec.row(0.0)), len(rec.headings()))

    def test_mismatch_is_reported(self):
        with self.assertLogs("stressmon.recorder", level="WARNING") as logs:
            Recorder([FakeSensor([("temp0",)], mismatch=1)]).row(0.0)
        self.assertIn("headings", "\n".join(logs.output))

    def test_sensors_without_csv_support_are_skipped(self):
        rec = Recorder([None, object(), FakeSensor([("temp0",)])])
        self.assertEqual(len(rec.headings()), 5)

    def test_prefix_columns_come_from_the_caller(self):
        rec = Recorder([FakeSensor([("temp0",)])], prefix=["RunID", "Runtime"])
        self.assertEqual(rec.row("R-1", 3.0), ["R-1", 3.0, 5.5, 6.0, 6.5, 7.0])

    def test_header_and_rows_read_back_with_equal_widths(self):
        rec = Recorder(self.sensors())
        fn = self.path("sensors.csv")
        write_header(fn, rec.headings())
        for _ in range(3):
            write_row(fn, rec.row(1.0))
        with open(fn, newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 4)
        self.assertEqual({len(row) for row in rows}, {len(rec.headings())})


class TestModelName(unittest.TestCase):
    """The model name is one line of a header; failing to read it is not fatal."""

    def setUp(self):
        self.original = recorder.run
        self.addCleanup(setattr, recorder, "run", self.original)

    def test_failure_is_unknown(self):
        def boom(*args, **kwargs):
            raise CalledProcessError(1, "dmidecode")
        recorder.run = boom
        self.assertEqual(recorder.get_model_name(), "Unknown")

    def test_os_error_is_unknown(self):
        def boom(*args, **kwargs):
            raise OSError("dmidecode not installed")
        recorder.run = boom
        self.assertEqual(recorder.get_model_name(), "Unknown")

    def test_blank_output_is_unknown(self):
        recorder.run = lambda *a, **k: type("Result", (), {"stdout": b"  \n"})()
        self.assertEqual(recorder.get_model_name(), "Unknown")

    def test_output_is_stripped(self):
        recorder.run = lambda *a, **k: type("Result", (), {"stdout": b"orion-x9\n"})()
        self.assertEqual(recorder.get_model_name(), "orion-x9")


class TestSummary(TempFileMixin):
    """The burn-in summary text shared by the monitors."""

    def parts(self):
        return dict(
            mhz=ModelSensor([("freq0",)]),
            ctemps=FakeSensor([("temp0",)]),
            watts=PowerSensor([("watt0",)]),
            fans=FakeSensor([("coretemp", "fan0")]),
            gpus=GpuSensor([("nvidia", "GPU0", "temp")]),
            drives=DriveSensor([("/dev/nvme0", "Temperature")]),
            usage=FakeSensor([("use0",)]),
            mem=SkuSensor([("Mem", "Used")], skus=("S7-A1",)),
        )

    def build(self, **overrides):
        parts = self.parts()
        parts.update(overrides)
        return build_summary(model_name="M-1", start_time="01-01-2026 00:00:00",
                             run_time=12.5, **parts)

    def test_sections_present(self):
        text = self.build()
        for expected in ("Model: M-1", "Runtime: 12.5", "CPU: Fake CPU Model",
                         "DIMM: S7-A1", "Fans", "GPUs", "Drives",
                         "nvidia - 550.54.14", "SubSystem: System76",
                         "Drive Model: model of /dev/nvme0"):
            self.assertIn(expected, text)

    def test_no_skus_still_writes_a_summary(self):
        """get_mem_skus() is None whenever dmidecode cannot be used.

        That used to raise inside the summary, and the update pool swallowed
        the error, so the .txt beside the CSV simply stopped being written.
        """
        text = self.build(mem=SkuSensor([("Mem", "Used")], skus=None))
        self.assertIn("Memory SKUs:", text)
        self.assertNotIn("DIMM:", text)

    def test_empty_sensors_are_skipped(self):
        text = self.build(ctemps=FakeSensor([]), watts=PowerSensor([]),
                          fans=FakeSensor([]), gpus=GpuSensor([]),
                          drives=DriveSensor([]))
        for section in ("Fans", "GPUs", "Drives"):
            self.assertNotIn(section, text)
        self.assertIn("Memory SKUs:", text)

    def test_gpu_rows_without_a_reading_are_skipped(self):
        class Null(GpuSensor):
            def get_current(self, params):
                return None
        text = self.build(gpus=Null([("nvidia", "GPU0", "temp")]))
        self.assertIn("GPU: GPU0", text)
        # the GPU table header is written, but the metric with no reading has
        # no row (the ctemps section above also starts with "temp0")
        self.assertFalse([line for line in text.splitlines()
                          if line.startswith("temp ")])

    def test_format_line_is_the_table_formatter(self):
        self.assertEqual(format_line(["a", 1], [5, 5], ['<', '>']), "a        1\n")


class TestColumnSummary(TempFileMixin):
    """The per-column summary the webui writes next to its CSV."""

    def test_min_max_mean(self):
        fn = self.path("summary.txt")
        write_column_summary(fn, "x.csv", ["Runtime", "Temp"],
                             [[1.0, 30.0], [2.0, 40.0], [3.0, 50.0]],
                             "01-01-2026 00:00:00")
        lines = self.read(fn).splitlines()
        temp = [line for line in lines if line.startswith("Temp")][0]
        self.assertEqual(temp.split(), ["Temp", "30.00", "50.00", "40.00"])

    def test_empty_cells_are_not_counted_as_zero(self):
        """Absent sensors leave empty placeholders in the row."""
        fn = self.path("summary.txt")
        write_column_summary(fn, "x.csv", ["Runtime", "Watts"],
                             [[1.0, 10.0], [2.0, ""], [3.0, 30.0]],
                             "01-01-2026 00:00:00")
        line = [line for line in self.read(fn).splitlines()
                if line.startswith("Watts")][0]
        self.assertEqual(line.split(), ["Watts", "10.00", "30.00", "13.33"])

    def test_no_rows_does_not_divide_by_zero(self):
        fn = self.path("summary.txt")
        write_column_summary(fn, "x.csv", ["Runtime"], [], "01-01-2026 00:00:00")
        self.assertIn("Log file: x.csv", self.read(fn))


if __name__ == "__main__":
    unittest.main()
