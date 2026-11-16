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
import uuid


def mkdir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_uuid():
    return str(uuid.uuid4())


def fsync_dir(path):
    """Make a rename or delete in the directory durable (it is only atomic until a
    power failure otherwise)."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
