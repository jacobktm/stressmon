"""The update pool class
"""

from concurrent.futures import ThreadPoolExecutor, wait


class UpdatePool:
    """UpdatePool class to asyncronously execute sensor updates
    """

    def __init__(self) -> None:
        self.update_pool = {}
        self.executor = None

    def __del__(self) -> None:
        if self.executor:
            self.executor.shutdown()

    def add_executor(self, classname, update_fn) -> None:
        """Add sensor.update function to update pool
        """
        self.update_pool[classname] = update_fn

    def do_updates(self, *args, **kwargs) -> None:
        """Perform updates asynchronously"""
        futures = []
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=len(self.update_pool.keys()))
        for _, func in self.update_pool.items():
            futures.append(self.executor.submit(func, *args, **kwargs))
        wait(futures)
