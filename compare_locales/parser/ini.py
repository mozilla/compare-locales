# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import re
from typing import Union

from .base import Entity, Entry, Junk, OffsetComment, Parser, Whitespace


class IniSection(Entry):
    """Entity-like object representing sections in ini files"""

    def __init__(self, ctx, span, val_span):
        self.ctx = ctx
        self.span = span
        self.key_span = self.val_span = val_span

    def __repr__(self):
        return self.raw_val


class IniParser(Parser):
    """
    Parse files of the form:
    # initial comment
    [cat]
    whitespace*
    #comment
    string=value
    ...
    """

    Comment = OffsetComment

    def __init__(self):
        self.reComment = re.compile("(?:^[;#][^\n]*\n)*(?:^[;#][^\n]*)", re.M)
        self.reSection = re.compile(r"\[(?P<val>.*?)\]", re.M)
        self.reKey = re.compile("(?P<key>.+?)=(?P<val>.*)", re.M)
        Parser.__init__(self)

    def getNext(
        self, ctx: Parser.Context, offset: int
    ) -> Union[Junk, OffsetComment, IniSection, Entity, Whitespace]:
        contents = ctx.contents
        m = self.reSection.match(contents, offset)
        if m:
            return IniSection(ctx, m.span(), m.span("val"))

        return super().getNext(ctx, offset)  # type: ignore

    def getJunk(self, ctx: Parser.Context, offset: int, *expressions) -> Junk:
        # base.Parser.getNext calls us with self.reKey, self.reComment.
        # Add self.reSection to the end-of-junk expressions
        expressions = expressions + (self.reSection,)
        return super().getJunk(ctx, offset, *expressions)
