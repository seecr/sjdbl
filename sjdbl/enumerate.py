## begin license ##
#
# "SJDBL"(Seecr Json Database Lib) provides a simple JSON store
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sjdbl"
#
# "sjdbl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import os
import threading

from .utils import fsync_dir


class Enumerator:
    def __init__(self, path, start=0):
        self._path = path
        self._lock = threading.Lock()
        if not self._path.exists():
            self._write_value(start)

    def increment(self):
        with self._lock:
            value = int(self._path.read_text())
            self._write_value(value + 1)
            return value

    def _write_value(self, value):
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w") as fp:
            fp.write(str(value))
            fp.flush()
            os.fsync(fp.fileno())
        tmp_path.replace(self._path)
        fsync_dir(self._path.parent)


class EnumerateValue:
    def __init__(self, name, start=0):
        self.name = name
        self.start = start
