from __future__ import annotations

import re
from typing import Iterable, List, Optional, Union

from ..parsers import Comment as ParserComment
from ..parsers import Entity as ParserEntity
from ..parsers import Junk as ParserJunk
from ..parsers import Whitespace as ParserWhitespace
from .elements import (
    Comment,
    Entry,
    Junk,
    Message,
    Pattern,
    PatternMessage,
    Text,
    VariableRef,
)


def patternFromPropertiesValue(
    value: str, variables: Optional[re.Pattern[str]] = None
) -> PatternMessage:
    """
    Compile a .properties value into a PatternMessage data class.

    `variables` may be a compiled regexp identifying a variable placeholder from the value.
    Its captured groups (if any) are ignored.
    """

    pattern: Pattern = []
    prevEnd = 0
    if variables:
        for match in variables.finditer(value):
            start = match.start()
            if start > prevEnd:
                pattern.append(Text(value[prevEnd:start]))
            pattern.append(VariableRef(match[0]))
            prevEnd = match.end()
    if len(pattern) == 0:
        pattern.append(Text(value))
    elif prevEnd < len(value):
        pattern.append(Text(value[prevEnd:]))
    return PatternMessage(pattern)


def resourceFromProperties(
    entries: Iterable[Union[ParserComment, ParserWhitespace, ParserEntity, ParserJunk]],
    variables: Optional[re.Pattern[str]] = None,
) -> List[Entry]:
    """
    Compile a parsed .properties file into a message resource.

    `variables` may be a compiled regexp identifying a variable placeholder.
    """

    res: List[Entry] = []
    for pe in entries:
        if isinstance(pe, ParserEntity):
            value = patternFromPropertiesValue(pe.val, variables)
            cspan = pe.pre_comment.span if pe.pre_comment else None
            res.append(Message((pe.key,), value, pe.span, cspan))
        elif isinstance(pe, ParserComment):
            res.append(Comment(pe.span))
        elif not isinstance(pe, ParserWhitespace):
            res.append(Junk(pe.span))
    return res
