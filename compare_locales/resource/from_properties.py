from __future__ import annotations

import re
from typing import Iterable, List, Optional, Union, cast

from ..parsers import Comment as ParserComment
from ..parsers import Entity as ParserEntity
from ..parsers import Junk as ParserJunk
from ..parsers import Whitespace as ParserWhitespace
from .elements import Message, Pattern, PatternMessage, Text, VariableRef
from .errors import ParseError

# All printf-ish formats, including Python's.
# Excludes Python's ` ` conversion flag, due to false positives -- https://github.com/mozilla/pontoon/issues/2988
printf = re.compile(
    r"%(?:\d\$|\(.*?\))?[-+0'#I]*[\d*]*(?:\.[\d*])?(?:hh?|ll?|[jLtz])?[%@AaCcdEeFfGginopSsuXx]"
)


def pattern(value: str, variables: Optional[re.Pattern[str]] = None) -> PatternMessage:
    """
    Compile a .properties value into a PatternMessage data class.

    `variables` may be a compiled regexp identifying a variable placeholder from the value.
    Its captured groups (if any) are ignored.
    """

    pattern: Pattern = []
    prev_end = 0
    if variables:
        for match in variables.finditer(value):
            (start, end) = match.span()
            if start > prev_end:
                pattern.append(Text(value[prev_end:start]))
            pattern.append(VariableRef(match[0]))
            prev_end = end
    if len(pattern) == 0 or prev_end < len(value):
        pattern.append(Text(value[prev_end:]))
    return PatternMessage(pattern)


def from_properties(
    entries: Iterable[Union[ParserComment, ParserWhitespace, ParserEntity, ParserJunk]],
    variables: Optional[re.Pattern[str]] = printf,
) -> List[Message]:
    """
    Compile a parsed .properties file into a message resource.

    `variables` may be a compiled regexp identifying a variable placeholder.
    """

    res: List[Message] = []
    for pe in entries:
        if isinstance(pe, ParserEntity):
            value = pattern(cast(str, pe.val), variables)
            if pe.pre_comment:
                lines = cast(str, pe.pre_comment.val).split("\n")
                comments = [re.sub(r"^[ \t]?", "", line, 1) for line in lines]
            else:
                comments = []
            res.append(Message((pe.key,), value, pe.span, comments))
        if isinstance(pe, ParserJunk):
            raise ParseError(f"Parse error: {pe}")
    return res
