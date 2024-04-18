# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from fluent.syntax import FluentParser, serialize

from .. import (
    CatchallKey,
    FunctionRef,
    Literal,
    Message,
    ParseError,
    PatternMessage,
    SelectMessage,
    Text,
    VariableRef,
    from_fluent,
    to_fluent,
)


class TestFluentParser(unittest.TestCase):
    def test_simple_message(self):
        src = "a = A\n"
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [Message(("a",), PatternMessage([Text("A")]))],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src)

    def test_complex_message(self):
        src = "abc = A { $arg } B { msg } C\n"
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [
                Message(
                    ("abc",),
                    PatternMessage(
                        [
                            Text("A "),
                            VariableRef("arg"),
                            Text(" B "),
                            FunctionRef("message", Literal(False, "msg")),
                            Text(" C"),
                        ]
                    ),
                )
            ],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src)

    def test_multiline_message(self):
        src = """\
abc =
    A
    B
    C
"""
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [Message(("abc",), PatternMessage([Text("A\nB\nC")]))],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src)

    def test_message_with_attribute(self):
        src = """\


abc = ABC
    .attr = Attr
"""
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [
                Message(("abc",), PatternMessage([Text("ABC")])),
                Message(("abc", "attr"), PatternMessage([Text("Attr")])),
            ],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src.lstrip())

    def test_message_with_attribute_and_no_value(self):
        src = """\
abc =
    .attr = Attr
"""
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [
                Message(("abc", "attr"), PatternMessage([Text("Attr")])),
            ],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src)

    def test_non_localizable(self):
        src = """\
### Resource Comment

foo = Foo

## Group Comment

-bar = Bar

# Standalone Comment

# Baz Comment
baz = Baz
"""
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [
                Message(("foo",), PatternMessage([Text("Foo")])),
                Message(
                    ("-bar",), PatternMessage([Text("Bar")]), comments=["Group Comment"]
                ),
                Message(
                    ("baz",),
                    PatternMessage([Text("Baz")]),
                    comments=["Group Comment", "Baz Comment"],
                ),
            ],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(
            str,
            """\
foo = Foo
# Group Comment
-bar = Bar
# Group Comment
# Baz Comment
baz = Baz
""",
        )

    def test_junk(self):
        src = """\
# Comment

Line of junk

# Comment
msg = value
"""
        ast = FluentParser().parse(src)
        try:
            from_fluent(ast)
            raise AssertionError("Expected parse error")
        except ParseError:
            pass

    def test_multiple_selectors(self):
        src = """\
abc =
    { $a ->
        [one]
            { $b ->
                [two] one-two
               *[other] one-other
            }
       *[other]
            { $b ->
                [two] other-two
               *[other] other-other
            }
    }
"""
        ast = FluentParser().parse(src)
        res = from_fluent(ast)
        self.assertEqual(
            res,
            [
                Message(
                    ("abc",),
                    SelectMessage(
                        selectors=[VariableRef("a"), VariableRef("b")],
                        variants=[
                            (
                                [Literal(False, "one"), Literal(False, "two")],
                                [Text("one-two")],
                            ),
                            (
                                [Literal(False, "one"), CatchallKey("other")],
                                [Text("one-other")],
                            ),
                            (
                                [CatchallKey("other"), Literal(False, "two")],
                                [Text("other-two")],
                            ),
                            (
                                [CatchallKey("other"), CatchallKey("other")],
                                [Text("other-other")],
                            ),
                        ],
                    ),
                )
            ],
        )
        str = serialize(to_fluent(res))
        self.assertEqual(str, src)
