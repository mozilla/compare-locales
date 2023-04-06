# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import re
from typing import Iterator, Optional, Tuple, Union, cast

from fluent.syntax import FluentParser as FTLParser
from fluent.syntax import ast as ftl
from fluent.syntax.serializer import serialize_comment
from fluent.syntax.visitor import Visitor

from .base import (
    CAN_SKIP,
    Comment,
    Entity,
    Entry,
    Junk,
    LiteralEntity,
    Parser,
    Whitespace,
)


class WordCounter(Visitor):
    def __init__(self) -> None:
        self.word_count = 0

    def generic_visit(self, node: ftl.BaseNode) -> None:
        if isinstance(node, (ftl.Span, ftl.Annotation, ftl.BaseComment)):
            return
        super().generic_visit(node)

    def visit_SelectExpression(self, node: ftl.SelectExpression) -> None:
        # optimize select expressions to only go through the variants
        self.visit(node.variants)

    def visit_TextElement(self, node: ftl.TextElement) -> None:
        self.word_count += len(node.value.split())


class FluentAttribute(Entry):
    ignored_fields = ["span"]

    def __init__(self, entity, attr_node):
        self.ctx = entity.ctx
        self.attr = attr_node
        self.key_span = (attr_node.id.span.start, attr_node.id.span.end)
        self.val_span = (attr_node.value.span.start, attr_node.value.span.end)

    def equals(self, other):
        if not isinstance(other, FluentAttribute):
            return False
        return self.attr.equals(other.attr, ignored_fields=self.ignored_fields)


class FluentEntity(Entity):
    # Fields ignored when comparing two entities.
    ignored_fields = ["comment", "span"]

    def __init__(
        self, ctx: Parser.Context, entry: Union[ftl.Message, ftl.Term]
    ) -> None:
        span = cast(ftl.Span, entry.span)
        start = span.start
        end = span.end

        self.ctx = ctx
        self.span = (start, end)

        id_span = cast(ftl.Span, entry.id.span)
        if isinstance(entry, ftl.Term):
            # Terms don't have their '-' as part of the id, use the prior
            # character
            self.key_span = (id_span.start - 1, id_span.end)
        else:
            # Message
            self.key_span = (id_span.start, id_span.end)

        if entry.value is not None:
            val_span = cast(ftl.Span, entry.value.span)
            self.val_span = (val_span.start, val_span.end)
        else:
            self.val_span = None

        self.entry = entry

        # Entry instances are expected to have pre_comment. It's used by
        # other formats to associate a Comment with an Entity. FluentEntities
        # don't need it because message comments are part of the entry AST and
        # are not separate Comment instances.
        self.pre_comment = None

    @property
    def root_node(self) -> Union[ftl.Message, ftl.Term]:
        """AST node at which to start traversal for count_words.

        By default we count words in the value and in all attributes.
        """
        return self.entry

    _word_count = None

    def count_words(self) -> int:
        if self._word_count is None:
            counter = WordCounter()
            counter.visit(self.root_node)
            self._word_count = counter.word_count

        return self._word_count

    def equals(self, other: Union[FluentTerm, FluentMessage]) -> bool:
        return self.entry.equals(other.entry, ignored_fields=self.ignored_fields)

    # In Fluent we treat entries as a whole.  FluentChecker reports errors at
    # offsets calculated from the beginning of the entry.
    def value_position(self, offset: Optional[int] = None) -> Tuple[int, int]:
        if offset is None:
            # no offset given, use our value start or id end
            if self.val_span:
                offset = self.val_span[0] - self.span[0]
            else:
                offset = self.key_span[1] - self.span[0]
        return self.position(offset)

    @property
    def attributes(self) -> Iterator[FluentAttribute]:
        for attr_node in self.entry.attributes:
            yield FluentAttribute(self, attr_node)

    def unwrap(self):
        return self.all

    def wrap(self, raw_val: str) -> LiteralEntity:
        """Create literal entity the given raw value.

        For Fluent, we're exposing the message source to tools like
        Pontoon.
        We also recreate the comment from this entity to the created entity.
        """
        all = raw_val
        if self.entry.comment is not None:
            all = serialize_comment(self.entry.comment) + all
        return LiteralEntity(self.key, raw_val, all)


class FluentMessage(FluentEntity):
    pass


class FluentTerm(FluentEntity):
    # Fields ignored when comparing two terms.
    ignored_fields = ["attributes", "comment", "span"]

    @property
    def root_node(self) -> Union[ftl.Pattern, None]:
        """AST node at which to start traversal for count_words.

        In Fluent Terms we only count words in the value. Attributes are
        private and do not count towards the word total.
        """
        return self.entry.value


class FluentComment(Comment):
    def __init__(
        self,
        ctx: Parser.Context,
        span: Tuple[int, int],
        entry: Union[ftl.Comment, ftl.GroupComment, ftl.ResourceComment],
    ) -> None:
        super().__init__(ctx, span)
        self._val_cache = entry.content


class FluentParser(Parser):
    capabilities = CAN_SKIP

    def __init__(self) -> None:
        super().__init__()
        self.ftl_parser = FTLParser()

    def walk(
        self, only_localizable: bool = False
    ) -> Iterator[Union[FluentTerm, FluentMessage, Whitespace, Junk, FluentComment]]:
        if not self.ctx:
            # loading file failed, or we just didn't load anything
            return

        resource = self.ftl_parser.parse(self.ctx.contents)

        last_span_end = 0

        for entry in resource.body:
            span = cast(ftl.Span, entry.span)
            if not only_localizable:
                if span.start > last_span_end:
                    yield Whitespace(self.ctx, (last_span_end, span.start))

            if isinstance(entry, ftl.Message):
                yield FluentMessage(self.ctx, entry)
            elif isinstance(entry, ftl.Term):
                yield FluentTerm(self.ctx, entry)
            elif isinstance(entry, ftl.Junk):
                start = span.start
                end = span.end
                if entry.content:
                    # strip leading whitespace
                    ms = re.match("[ \t\r\n]*", entry.content)
                    if ms and ms.end() > 0:
                        start += ms.end()
                        if not only_localizable:
                            yield Whitespace(self.ctx, (span.start, start))
                    # strip trailing whitespace
                    me = re.search("[ \t\r\n]*$", entry.content)
                    if me:
                        ws, we = me.span()
                        end -= we - ws
                yield Junk(self.ctx, (start, end))
                if not only_localizable and end < span.end:
                    yield Whitespace(self.ctx, (end, span.end))
            elif isinstance(entry, ftl.BaseComment) and not only_localizable:
                span_ = (span.start, span.end)
                yield FluentComment(self.ctx, span_, entry)

            last_span_end = span.end

        # Yield Whitespace at the EOF.
        if not only_localizable:
            eof_offset = len(self.ctx.contents)
            if eof_offset > last_span_end:
                yield Whitespace(self.ctx, (last_span_end, eof_offset))
