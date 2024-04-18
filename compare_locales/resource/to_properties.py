from __future__ import annotations

from re import sub
from typing import List

from .elements import Message, Pattern, PatternMessage, Text, VariableRef


def escape(str: str, as_key: bool) -> str:
    """
    For keys, escape all control chars,  whitespace, `:`, and `=`.

    For values, escape control chars, leading & trailing spaces + all other whitespace.
    Values with an internal newline are split across multiple indented natural lines.
    """

    indent = "\\\n  "

    def repl(match):
        m = match.group(0)
        if m == "\n":
            return r"\n" if as_key else rf"\n{indent}"
        elif m == "\r":
            return r"\r"
        elif m == "\t":
            return r"\t"
        elif m == " " or m == ":" or m == "=" or m == "\\":
            return rf"\{m}"
        else:
            return rf"\u{ord(m):0{4}x}"

    if as_key:
        return sub(r"[\x00-\x1f\x7f-\x9f\s:=\\]", repl, str)
    else:
        res = sub(r"(?ms)^ | $|\n(?=.)|[\x00-\x09\x0b-\x1f\x7f-\x9f\\]", repl, str)
        res = sub(r"\n$", "\\n", res)
        return indent + res if "\n" in res else res


def join_pattern(pattern: Pattern) -> str:
    res = ""
    for part in pattern:
        if isinstance(part, Text):
            res += part.value
        elif isinstance(part, VariableRef):
            res += part.name
        else:
            raise Exception(f"Unsupported expression: {part}")
    return res


def to_properties(entries: List[Message]) -> str:
    str = ""
    for msg in entries:
        if len(msg.key) != 1:
            raise Exception(f"Unsupported key: {msg.key}")
        if not isinstance(msg.value, PatternMessage):
            raise Exception(f"Unsupported message type: {msg.value}")
        for line in msg.comments or []:
            str += sub(r"(?m)^", "# ", line.rstrip()) + "\n"
        key = escape(msg.key[0], as_key=True)
        value = escape(join_pattern(msg.value.pattern), as_key=False)
        str += f"{key} = {value}\n"
    return str
