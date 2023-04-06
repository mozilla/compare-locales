# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import bisect
import codecs
import re
from collections import Counter
from typing import Iterator, List, Literal, Optional, Tuple, Union, overload

from ..keyedtuple import KeyedTuple
from ..paths import File

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


class Entry:
    """
    Abstraction layer for a localizable entity.
    Currently supported are grammars of the form:

    1: entity definition
    2: entity key (name)
    3: entity value

    <!ENTITY key "value">

    <--- definition ---->
    """

    def __init__(
        self,
        ctx: Parser.Context,
        pre_comment: Optional[Comment],
        inner_white: Optional[Whitespace],
        span: Tuple[int, int],
        key_span: Tuple[int, int],
        val_span: Tuple[int, int],
    ) -> None:
        self.ctx = ctx
        self.span = span
        self.key_span = key_span
        self.val_span = val_span
        self.pre_comment = pre_comment
        self.inner_white = inner_white

    def position(self, offset: int = 0) -> Tuple[int, int]:
        """Get the 1-based line and column of the character
        with given offset into the Entity.

        If offset is negative, return the end of the Entity.
        """
        if offset < 0:
            pos = self.span[1]
        else:
            pos = self.span[0] + offset
        return self.ctx.linecol(pos)

    def value_position(self, offset: int = 0) -> Tuple[int, int]:
        """Get the 1-based line and column of the character
        with given offset into the value.

        If offset is negative, return the end of the value.
        """
        assert self.val_span is not None
        if offset < 0:
            pos = self.val_span[1]
        else:
            pos = self.val_span[0] + offset
        return self.ctx.linecol(pos)

    def _span_start(self) -> int:
        start = self.span[0]
        if hasattr(self, "pre_comment") and self.pre_comment is not None:
            start = self.pre_comment.span[0]
        return start

    @property
    def all(self) -> str:
        start = self._span_start()
        end = self.span[1]
        return self.ctx.contents[start:end]

    @property
    def key(self) -> str:
        return self.ctx.contents[self.key_span[0] : self.key_span[1]]

    @property
    def raw_val(self) -> Union[str, None]:
        if self.val_span is None:
            return None
        return self.ctx.contents[self.val_span[0] : self.val_span[1]]

    @property
    def val(self) -> Union[str, None]:
        return self.raw_val

    def __repr__(self) -> str:
        return self.key

    re_br = re.compile("<br[ \t\r\n]*/?>", re.U)
    re_sgml = re.compile(r"</?\w+.*?>", re.U | re.M)

    def count_words(self) -> int:
        """Count the words in an English string.
        Replace a couple of xml markup to make that safer, too.
        """
        value = self.val
        if value is None:
            return 0
        value = self.re_br.sub("\n", value)
        value = self.re_sgml.sub("", value)
        return len(value.split())

    def equals(self, other: Entity) -> bool:
        return self.key == other.key and self.val == other.val


class StickyEntry(Entry):
    """Subclass of Entry to use in for syntax fragments
    which should always be overwritten in the serializer.
    """

    pass


class Entity(Entry):
    @property
    def localized(self) -> bool:
        """Is this entity localized.

        Always true for monolingual files.
        In bilingual files, this is a dynamic property.
        """
        return True

    def unwrap(self) -> Optional[str]:
        """Return the literal value to be used by tools."""
        return self.raw_val

    def wrap(self, raw_val: str) -> LiteralEntity:
        """Create literal entity based on reference and raw value.

        This is used by the serialization logic.
        """
        start = self._span_start()
        all = (
            self.ctx.contents[start : self.val_span[0]]
            + raw_val
            + self.ctx.contents[self.val_span[1] : self.span[1]]
        )
        return LiteralEntity(self.key, raw_val, all)


class LiteralEntity(Entity):
    """Subclass of Entity to represent entities without context slices.

    It's storing string literals for key, raw_val and all instead of spans.
    """

    def __init__(self, key: str, val: str, all: str) -> None:
        super().__init__(None, None, None, None, None, None)  # type: ignore
        self._key = key
        self._raw_val = val
        self._all = all

    @property
    def key(self) -> str:
        return self._key

    @property
    def raw_val(self) -> str:
        return self._raw_val

    @property
    def all(self) -> str:
        return self._all


class PlaceholderEntity(LiteralEntity):
    """Subclass of Entity to be removed in merges."""

    def __init__(self, key: str) -> None:
        super().__init__(key, "", "\nplaceholder\n")


class Comment(Entry):
    def __init__(self, ctx: Parser.Context, span: Tuple[int, int]) -> None:
        self.ctx = ctx
        self.span = span
        self.val_span = None  # type:ignore
        self._val_cache: Optional[str] = None

    @property
    def key(self) -> None:  # type:ignore[override]
        return None

    @property
    def val(self) -> str:
        if self._val_cache is None:
            self._val_cache = self.all
        return self._val_cache

    def __repr__(self) -> str:
        return self.all


class OffsetComment(Comment):
    """Helper for file formats that have a constant number of leading
    chars to strip from comments.
    Offset defaults to 1
    """

    comment_offset = 1

    @property
    def val(self) -> str:
        if self._val_cache is None:
            self._val_cache = "".join(
                line[self.comment_offset :] for line in self.all.splitlines(True)
            )
        return self._val_cache


class Junk:
    """
    An almost-Entity, representing junk data that we didn't parse.
    This way, we can signal bad content as stuff we don't understand.
    And the either fix that, or report real bugs in localizations.
    """

    junkid = 0

    def __init__(
        self,
        ctx: Parser.Context,
        span: Tuple[int, int],
    ) -> None:
        self.ctx = ctx
        self.span = span
        self.__class__.junkid += 1
        self.key = "_junk_%d_%d-%d" % (self.__class__.junkid, span[0], span[1])

    def position(self, offset: int = 0) -> Tuple[int, int]:
        """Get the 1-based line and column of the character
        with given offset into the Entity.

        If offset is negative, return the end of the Entity.
        """
        if offset < 0:
            pos = self.span[1]
        else:
            pos = self.span[0] + offset
        return self.ctx.linecol(pos)

    @property
    def all(self) -> str:
        return self.ctx.contents[self.span[0] : self.span[1]]

    @property
    def raw_val(self) -> str:
        return self.all

    @property
    def val(self) -> str:
        return self.all

    def error_message(self) -> str:
        params = (self.val,) + self.position() + self.position(-1)
        return (
            'Unparsed content "%s" from line %d column %d'
            " to line %d column %d" % params
        )

    def __repr__(self) -> str:
        return self.key


class Whitespace(Entry):
    """Entity-like object representing an empty file with whitespace,
    if allowed
    """

    raw_val: str
    val: str

    def __init__(self, ctx: Parser.Context, span: Tuple[int, int]) -> None:
        self.ctx = ctx
        self.span = self.key_span = self.val_span = span

    def __repr__(self) -> str:
        return self.raw_val


class BadEntity(ValueError):
    """Raised when the parser can't create an Entity for a found match."""

    pass


Comment_ = Comment


class Parser:
    capabilities = CAN_SKIP | CAN_MERGE
    reWhitespace = re.compile("[ \t\r\n]+", re.M)
    Comment = Comment
    # NotImplementedError would be great, but also tedious
    reKey: re.Pattern[str] = None  # type: ignore
    reComment: re.Pattern[str] = None  # type: ignore

    class Context:
        "Fixture for content and line numbers"

        def __init__(self, contents: str):
            self.contents = contents
            # cache split lines
            self._lines: Optional[List[int]] = None

        def linecol(self, position: int) -> Tuple[int, int]:
            "Returns 1-based line and column numbers."
            if self._lines is None:
                nl = re.compile("\n", re.M)
                self._lines = [m.end() for m in nl.finditer(self.contents)]

            line_offset = bisect.bisect(self._lines, position)
            line_start = self._lines[line_offset - 1] if line_offset else 0
            col_offset = position - line_start

            return line_offset + 1, col_offset + 1

    def __init__(self) -> None:
        if not hasattr(self, "encoding"):
            self.encoding = "utf-8"
        self.ctx: Optional[Parser.Context] = None

    def readFile(self, file: Union[str, File]) -> None:
        """Read contents from disk, with universal_newlines"""
        if isinstance(file, File):
            file = file.fullpath
        # python 2 has binary input with universal newlines,
        # python 3 doesn't. Let's split code paths
        with open(file, encoding=self.encoding, errors="replace", newline=None) as f:
            self.readUnicode(f.read())

    def readContents(self, contents: bytes) -> None:
        """Read contents and create parsing context.

        contents are in native encoding, but with normalized line endings.
        """
        (string, _) = codecs.getdecoder(self.encoding)(contents, "replace")
        self.readUnicode(string)

    def readUnicode(self, contents: str) -> None:
        self.ctx = self.Context(contents)

    def parse(self) -> KeyedTuple:
        return KeyedTuple(self)

    def __iter__(self) -> Iterator[Union[Entity, Junk]]:
        return self.walk(only_localizable=True)

    @overload
    def walk(self, only_localizable: Literal[True]) -> Iterator[Union[Entity, Junk]]:
        ...

    @overload
    def walk(
        self, only_localizable: bool = False
    ) -> Iterator[Union[Entity, Junk, Comment_, Whitespace]]:
        ...

    def walk(
        self, only_localizable: bool = False
    ) -> Iterator[Union[Entity, Junk, Comment_, Whitespace]]:
        if not self.ctx:
            # loading file failed, or we just didn't load anything
            return
        ctx = self.ctx
        contents = ctx.contents

        next_offset = 0
        while next_offset < len(contents):
            entity = self.getNext(ctx, next_offset)

            if isinstance(entity, (Entity, Junk)) or not only_localizable:
                yield entity

            next_offset = entity.span[1]

    def getNext(
        self, ctx: Parser.Context, offset: int
    ) -> Union[Entity, Junk, Comment_, Whitespace]:
        """Parse the next fragment.

        Parse comments first, then white-space.
        If an entity follows, create that entity with such pre_comment and
        inner white-space. If not, emit comment or white-space as standlone.
        It's OK that this might parse whitespace more than once.
        Comments are associated with entities if they're not separated by
        blank lines. Multiple consecutive comments are joined.
        """
        junk_offset = offset
        m = self.reComment.match(ctx.contents, offset)
        if m:
            current_comment = self.Comment(ctx, m.span())
            if offset < 2 and "License" in current_comment.val:
                # Heuristic. A early comment with "License" is probably
                # a license header, and should be standalone.
                # Not glueing ourselves to offset == 0 as we might have
                # skipped a BOM.
                return current_comment
            offset = m.end()
        else:
            current_comment = None
        m = self.reWhitespace.match(ctx.contents, offset)
        if m:
            white_space = Whitespace(ctx, m.span())
            offset = m.end()
            if current_comment is not None and white_space.raw_val.count("\n") > 1:
                # standalone comment
                # return the comment, and reparse the whitespace next time
                return current_comment
            if current_comment is None:
                return white_space
        else:
            white_space = None
        m = self.reKey.match(ctx.contents, offset)
        if m:
            try:
                return self.createEntity(ctx, m, current_comment, white_space)
            except BadEntity:
                # fall through to Junk, probably
                pass
        if current_comment is not None:
            return current_comment
        if white_space is not None:
            return white_space
        return self.getJunk(ctx, junk_offset, self.reKey, self.reComment)

    def getJunk(
        self,
        ctx: Parser.Context,
        offset: int,
        *expressions: re.Pattern[str],
    ) -> Junk:
        junkend: Optional[int] = None
        for exp in expressions:
            m = exp.search(ctx.contents, offset)
            if m:
                junkend = min(junkend, m.start()) if junkend else m.start()
        return Junk(ctx, (offset, junkend or len(ctx.contents)))

    def createEntity(
        self,
        ctx: Parser.Context,
        m: re.Match[str],
        current_comment: Optional[Comment_],
        white_space: Optional[Whitespace],
    ) -> Entity:
        return Entity(
            ctx, current_comment, white_space, m.span(), m.span("key"), m.span("val")
        )

    @classmethod
    def findDuplicates(cls, entities: KeyedTuple) -> Iterator[str]:
        found = Counter(entity.key for entity in entities)
        for entity_id, cnt in found.items():
            if cnt > 1:
                yield f"{entity_id} occurs {cnt} times"
