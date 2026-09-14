## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Swindl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Swindl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##


class Enumerator:
    def __init__(self, path, start=0):
        self._path = path
        if not self._path.exists():
            self._write_value(start)

    def increment(self):
        value = int(self._path.read_text())
        self._write_value(value + 1)
        return value

    def _write_value(self, value):
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(str(value))
        tmp_path.rename(self._path)


class EnumerateValue:
    def __init__(self, name, start=0):
        self.name = name
        self.start = start
