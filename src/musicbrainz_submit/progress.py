import sys
from queue import Queue
from threading import Thread

import tqdm


class Progress(Thread):
    def __init__(self, queue: Queue[str | tuple[str, int] | None]):
        super().__init__()
        self.queue: Queue[str | tuple[str, int] | None] = queue
        print("")  # Empty line to be used for status bar
        self.bar = tqdm.tqdm(total=1)
        self.per_name: dict[str, list[int]] = {}

    @staticmethod
    def update_status_line(text, width=80):
        """Print a single-line status message above the progress bar."""
        # Cut off if too long
        line = text[:width]
        # Move cursor up one line, clear it, and print new text
        sys.stdout.write(f"\033[F\033[K{line}\n")
        sys.stdout.flush()

    def full_update(self):
        self.update_status_line(
            ", ".join(name for name, (total, current) in self.per_name.items() if total > current)
        )

    def run(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            if isinstance(item, str):
                self.per_name[item][1] += 1
                self.bar.update(1)
                self.full_update()
            else:
                name, total = item
                previous, previous_count = self.per_name.get(name, [0, 0])
                self.per_name[name] = [total + previous, previous_count]
                self.bar.total = sum(i[0] for i in self.per_name.values())
                self.bar.refresh()
                self.full_update()
            self.queue.task_done()
        self.bar.close()
