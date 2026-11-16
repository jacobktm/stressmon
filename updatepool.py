"""The update pool class
"""

import logging
from concurrent.futures import ThreadPoolExecutor, wait

log = logging.getLogger(__name__)


class UpdatePool:
    """UpdatePool class to asyncronously execute sensor updates
    """

    def __init__(self) -> None:
        self.update_pool = {}
        self.executor = None
        self.errors = {}

    def __del__(self) -> None:
        if self.executor:
            self.executor.shutdown()

    def add_executor(self, classname, update_fn) -> None:
        """Add sensor.update function to update pool
        """
        self.update_pool[classname] = update_fn

    def do_updates(self, *args, **kwargs) -> None:
        """Perform updates asynchronously"""
        futures = {}
        if self.executor is None:
            # max_workers must be at least one; an empty pool (no sensors
            # detected) would otherwise raise ValueError here.
            self.executor = ThreadPoolExecutor(max_workers=max(1, len(self.update_pool)))
        for classname, func in self.update_pool.items():
            futures[self.executor.submit(func, *args, **kwargs)] = classname
        wait(futures)
        # A future's exception is otherwise dropped on the floor: the sensor
        # stops updating and every reading it owns just goes stale, which is
        # very hard to notice in a log captured overnight.
        for future, classname in futures.items():
            error = future.exception()
            if error is None:
                if classname in self.errors:
                    log.info("Sensor %s updating again", classname)
                    self.errors.pop(classname, None)
                continue
            message = f"{type(error).__name__}: {error}"
            if self.errors.get(classname) != message:
                log.error("Sensor %s update failed: %s", classname, message)
            self.errors[classname] = message

    def get_errors(self) -> dict:
        """Return {classname: message} for sensors whose last update failed."""
        return dict(self.errors)
