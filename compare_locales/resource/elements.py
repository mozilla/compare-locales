from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, OrderedDict, Tuple, Union


# PATTERN


@dataclass
class CatchallKey:
    "The catch-all variant key matches all values."

    value: Optional[str] = field(compare=False, default=None)


@dataclass
class FunctionRef:
    """
    To resolve a FunctionRef, an externally defined function is called.

    The `name` identifies a function that takes in the arguments `args`, the
    current locale, as well as any `options`, and returns some corresponding
    output. Likely functions available by default would include `'plural'` for
    determining the plural category of a numeric value, as well as `'number'`
    and `'date'` for formatting values.
    """

    name: str
    operand: Union[Literal, VariableRef, None] = None
    options: OrderedDict[str, Union[Literal, VariableRef]] = field(
        default_factory=OrderedDict
    )


@dataclass
class Literal:
    """An immediately defined value.

    Always contains a string value. In Function arguments and options,
    the expected type of the value may result in the value being
    further parsed as a boolean or a number.
    """

    quoted: bool
    value: str


@dataclass
class Text:
    "Top-level literal content."

    value: str


@dataclass
class VariableRef:
    """
    The value of a VariableRef is defined by the current Scope.

    To refer to an inner property of an object value, use `.` as a separator
    in case of conflict, the longest starting substring wins.
    For example, `'user.name'` would be first matched by an exactly matching top-level key,
    and in case that fails, with the `'name'` property of the `'user'` object:
    The runtime scopes `{ 'user.name': 'Kat' }` and `{ user: { name: 'Kat' } }`
    would both resolve a `'user.name'` VariableRef as the string `'Kat'`.
    """

    name: str


Expression = Union[FunctionRef, Literal, VariableRef]

OptionValue = Union[Literal, VariableRef]

Pattern = List[Union[Expression, Text]]
"""
The body of each message is composed of a sequence of parts, some of them fixed (Text),
others placeholders for values depending on additional data.
"""

VariantKey = Union[Literal, CatchallKey]


# MESSAGE


@dataclass
class PatternMessage:
    """
    A single message with no variants.
    """

    pattern: Pattern
    declarations: Declarations = field(default_factory=OrderedDict)


@dataclass
class SelectMessage:
    """
    SelectMessage generalises the plural, selectordinal and select
    argument types of MessageFormat 1.
    Each case is defined by a key of one or more string identifiers,
    and selection between them is made according to
    the values of a corresponding number of placeholders.
    The result of the selection is always a single Pattern.
    """

    selectors: List[Expression]
    variants: List[Tuple[List[VariantKey], Pattern]]
    declarations: Declarations = field(default_factory=OrderedDict)


Declarations = OrderedDict[str, Expression]
"""
A message may declare any number of local variables or aliases,
each with a value defined by an expression.
Earlier declarations may not refer to values that are defined later.
"""


# RESOURCE


@dataclass
class Message:
    """
    The representation of a single message.
    Depending on the source format, `key` may include more than one part.
    For example, Fluent attributes use a `(str, str)` key.
    The shape of the `value` is an implementation detail,
    and may vary for the same message in different languages.

    The `span` position in the source is not used in comparisons,
    and defaults to `(-1, -1)`.
    """

    key: Tuple[str, ...]
    value: Union[PatternMessage, SelectMessage]
    span: Span = field(compare=False, default=(-1, -1))
    comments: List[str] = field(default_factory=list)


Span = Tuple[int, int]
"The 0-indexed `[start, end)` character range of a resource item."
