import time
from typing import Optional

class Profiler:
    def __init__(self):
        self.start_time = None
        self.ttft = None
        self.end_time = None

    def start(self):
        self.start_time = time.monotonic()

    def first_token(self):
        if self.ttft is None:
            self.ttft = time.monotonic() - self.start_time

    def end(self):
        self.end_time = time.monotonic()

    @property
    def latency(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def ttft_value(self) -> Optional[float]:
        return self.ttft
