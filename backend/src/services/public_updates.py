"""Read only complete strings in the explicit public updates field.

Never forward arbitrary JSON deltas, reasoning tokens or other structured fields.
If the model does not place updates first, nothing is exposed.
"""

import json
from collections.abc import Callable


class PublicUpdates:
    def __init__(self, publish: Callable[[str], None]):
        self.publish = publish
        self.buffer = ""
        self.offset: int | None = None
        self.stopped = False
        self.emitted = 0

    def feed(self, delta: str) -> None:
        if self.stopped:
            return
        self.buffer += delta
        if len(self.buffer) > 16384:
            self.stopped = True
            return
        decoder = json.JSONDecoder()
        if self.offset is None:
            text = self.buffer.lstrip()
            if not text.startswith("{"):
                return
            start = len(self.buffer) - len(text) + 1
            start += len(self.buffer[start:]) - len(self.buffer[start:].lstrip())
            try:
                key, end = decoder.raw_decode(self.buffer, start)
            except ValueError:
                return
            if key != "updates":
                self.stopped = True
                return
            suffix = self.buffer[end:].lstrip()
            if not suffix.startswith(":"):
                return
            suffix = suffix[1:].lstrip()
            if not suffix.startswith("["):
                return
            self.offset = len(self.buffer) - len(suffix) + 1
        while True:
            cursor = self.offset
            while cursor < len(self.buffer) and self.buffer[cursor] in " \r\n\t,":
                cursor += 1
            if cursor >= len(self.buffer):
                return
            if self.buffer[cursor] == "]":
                self.stopped = True
                return
            try:
                value, end = decoder.raw_decode(self.buffer, cursor)
            except ValueError:
                return
            if not isinstance(value, str):
                self.stopped = True
                return
            self.offset = end
            if value.strip():
                self.publish(value.strip())
                self.emitted += 1
