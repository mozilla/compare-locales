# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from compare_locales.keyedtuple import KeyedTuple
from compare_locales.parsers import (
    CAN_NONE,
    CAN_COPY,
    CAN_SKIP,
    CAN_MERGE,
    AndroidParser,
    DefinesInstruction,
    DefinesParser,
    DTDEntity,
    DTDParser,
    FluentComment,
    FluentEntity,
    FluentMessage,
    FluentParser,
    FluentTerm,
    IniParser,
    IniSection,
    PoParser,
    PropertiesEntity,
    PropertiesParser,
    Entry,
    Entity,
    Comment,
    OffsetComment,
    Junk,
    Whitespace,
    BadEntity,
    Parser,
)
from compare_locales.paths import File

__all__ = [
    "CAN_NONE",
    "CAN_COPY",
    "CAN_SKIP",
    "CAN_MERGE",
    "Junk",
    "Entry",
    "Entity",
    "Whitespace",
    "Comment",
    "OffsetComment",
    "BadEntity",
    "Parser",
    "AndroidParser",
    "DefinesParser",
    "DefinesInstruction",
    "DTDParser",
    "DTDEntity",
    "FluentParser",
    "FluentComment",
    "FluentEntity",
    "FluentMessage",
    "FluentTerm",
    "IniParser",
    "IniSection",
    "PoParser",
    "PropertiesParser",
    "PropertiesEntity",
]

__constructors = []


def patchParser(parser):
    "Monkeypatch the parser with methods that depend on compare-locales"

    def parse(self):
        return KeyedTuple(self)

    def readFile(self, file):
        """Read contents from disk, with universal_newlines"""
        if isinstance(file, File):
            file = file.fullpath
        with open(file, encoding=self.encoding, errors="replace", newline=None) as f:
            self.readUnicode(f.read())

    parser.__class__.parse = parse
    parser.__class__.readFile = readFile
    return parser


def getParser(path):
    for item in __constructors:
        if re.search(item[0], path):
            return patchParser(item[1])
    try:
        from pkg_resources import iter_entry_points

        for entry_point in iter_entry_points("compare_locales.parsers"):
            p = entry_point.resolve()()
            if p.use(path):
                return patchParser(p)
    except (ImportError, OSError):
        pass
    raise UserWarning("Cannot find Parser")


def hasParser(path):
    try:
        return bool(getParser(path))
    except UserWarning:
        return False


__constructors = [
    ("strings.*\\.xml$", AndroidParser()),
    ("\\.dtd$", DTDParser()),
    ("\\.properties$", PropertiesParser()),
    ("\\.ini$", IniParser()),
    ("\\.inc$", DefinesParser()),
    ("\\.ftl$", FluentParser()),
    ("\\.pot?$", PoParser()),
]
