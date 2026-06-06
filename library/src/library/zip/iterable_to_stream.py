import io
from typing import Optional


def iterable_to_stream(iterable, buffer_size=io.DEFAULT_BUFFER_SIZE):
    """
    Lets you use an iterable (e.g. a generator) that yields bytestrings as a read-only
    input stream.

    The stream implements Python 3's newer I/O API (available in Python 2's io module).
    For efficiency, the stream is buffered.
    """

    class IterStream(io.RawIOBase):
        def __init__(self):
            self.leftover = None

        def readable(self):
            return True

        def readinto(self, b):
            try:
                l = len(b)  # We're supposed to return at most this much
                chunk = self.leftover or next(iterable)
                output, self.leftover = chunk[:l], chunk[l:]
                b[: len(output)] = output
                return len(output)
            except StopIteration:
                return 0  # indicate EOF

    return io.BufferedReader(IterStream(), buffer_size=buffer_size)


# Source - https://stackoverflow.com/a/20260030
# Posted by Mechanical snail
# Retrieved 2026-06-04, License - CC BY-SA 3.0

with iterable_to_stream(str(x**2).encode("utf8") for x in range(11)) as s:
    print(s.read())


# Source - https://stackoverflow.com/a/6658949
# Posted by shazow, modified by community. See post 'Timeline' for change history
# Retrieved 2026-06-04, License - CC BY-SA 3.0


class IterStreamer(object):
    """
    File-like streaming iterator.
    """

    def __init__(self, generator):
        self.generator = generator
        self.iterator = iter(generator)
        self.leftover = ""

    def __len__(self):
        return self.generator.__len__()

    def __iter__(self):
        return self.iterator

    def next(self):
        return self.iterator.next()

    def read(self, size):
        data = self.leftover
        count = len(self.leftover)

        if count < size:
            try:
                while count < size:
                    chunk = self.next()
                    data += chunk
                    count += len(chunk)
            except StopIteration:
                pass

        self.leftover = data[size:]

        return data[:size]


class iter_to_stream(object):
    def __init__(self, iterable):
        self.buffered = ""
        self.iter = iter(iterable)

    def read(self, size):
        result = ""
        while size > 0:
            data = self.buffered or next(self.iter, None)
            self.buffered = ""
            if data is None:
                break
            size -= len(data)
            if size < 0:
                data, self.buffered = data[:size], data[size:]
            result += data
        return result


# Source - https://stackoverflow.com/a/63418620
# Posted by andrii, modified by community. See post 'Timeline' for change history
# Retrieved 2026-06-04, License - CC BY-SA 4.0


class IteratorReader(io.RawIOBase):
    def __init__(self, iterator):
        self.iterator = iterator
        self.leftover = []

    def readinto(self, buffer: bytearray) -> Optional[int]:
        size = len(buffer)
        while len(self.leftover) < size:
            try:
                self.leftover.extend(next(self.iterator))
            except StopIteration:
                break

        if len(self.leftover) == 0:
            return 0

        output, self.leftover = self.leftover[:size], self.leftover[size:]
        buffer[: len(output)] = output
        return len(output)

    def readable(self) -> bool:
        return True
