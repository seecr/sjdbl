## begin license ##
#
# "SJDBL"(Seecr Json Database Lib) provides a simple JSON store
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sjdbl"
#
# "sjdbl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "sjdbl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "sjdbl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

"""Revisions, HasChangedException and archiving."""

from pathlib import Path
from tempfile import TemporaryDirectory

from sjdbl import Store
from sjdbl.base import Base, HasChangedException
from sjdbl.field import Field


class Note(Base):
    FIELDS = [Field.text("text")]


def main(path):
    store = Store(path=path, models=[Note])

    note = Note.create(text="first version")
    store.put(note)
    print("qrid after put:", note.qrid)

    note.update(text="edited in memory")
    print("qrid after update (unchanged):", note.qrid)
    store.put(note)
    print("qrid after put (new revision):", note.qrid)

    alice = store.get(note.qid)
    bob = store.get(note.qid)

    alice.update(text="Alice was here")
    store.put(alice)

    bob.update(text="Bob was here")
    try:
        store.put(bob)
    except HasChangedException as e:
        print("conflict for:", e)

    bob = store.get(note.qid)
    print("Bob reloads and sees:", bob.text)
    bob.update(text=bob.text + ", and Bob too")
    store.put(bob)
    print("stored:", store.get(note.qid).text)

    bob.mark_archived(store)
    print("archived:", store.get(note.qid).is_archived)

    try:
        alice.mark_archived(store, archived=False)
    except HasChangedException:
        print("Alice's copy is stale, archiving it again is refused")


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
