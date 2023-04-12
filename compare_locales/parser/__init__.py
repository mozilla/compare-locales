# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

from compare_locales.keyedtuple import KeyedTuple
from compare_locales.parsers import (
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

# The allowed capabilities for the Parsers.  They define the exact strategy
# used by ContentComparer.merge.

# Don't perform any merging
CAN_NONE = 0
# Copy the entire reference file
CAN_COPY = 1
# Remove broken entities from localization
# Without CAN_MERGE, en-US is not good to use for localization.
CAN_SKIP = 2
# Add missing and broken entities from the reference to localization
# This effectively means that en-US is good to use for localized files.
CAN_MERGE = 4

__constructors = [
    # Android does l10n fallback at runtime, don't merge en-US strings
    ("strings.*\\.xml$", AndroidParser(), CAN_SKIP),
    ("\\.dtd$", DTDParser(), CAN_SKIP | CAN_MERGE),
    ("\\.properties$", PropertiesParser(), CAN_SKIP | CAN_MERGE),
    ("\\.ini$", IniParser(), CAN_SKIP | CAN_MERGE),
    # can't merge, #unfilter needs to be the last item, which we don't support
    ("\\.inc$", DefinesParser(), CAN_COPY),
    # Fluent does l10n fallback at runtime, don't merge en-US strings
    ("\\.ftl$", FluentParser(), CAN_SKIP),
    # gettext does l10n fallback at runtime, don't merge en-US strings
    ("\\.pot?$", PoParser(), CAN_SKIP),
]


def patchParser(parser, capabilities=CAN_SKIP | CAN_MERGE):
    "Monkeypatch the parser with methods that depend on compare-locales"

    def parse(self):
        return KeyedTuple(self)

    def readFile(self, file):
        """Read contents from disk, with universal_newlines"""
        if isinstance(file, File):
            file = file.fullpath
        with open(file, encoding=self.encoding, errors="replace", newline=None) as f:
            self.readUnicode(f.read())

    parser.__class__.capabilities = capabilities
    parser.__class__.parse = parse
    parser.__class__.readFile = readFile
    return parser


def getParser(path):
    for item in __constructors:
        if re.search(item[0], path):
            return patchParser(item[1], item[2])
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
