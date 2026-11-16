"""Tests for stressmon.

Run them from the stress-scripts checkout, which is where stressmon is used:

    python -m unittest discover -s stressmon/tests -t .
"""

import logging

# Deliberate failures are part of what these tests exercise; keep their log
# records out of the test output.  assertLogs() still captures them.
logging.getLogger().addHandler(logging.NullHandler())
