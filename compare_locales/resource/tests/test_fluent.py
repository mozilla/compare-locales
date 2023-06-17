# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from fluent.syntax import FluentParser

from .. import (
    Comment,
    FunctionRef,
    Junk,
    Literal,
    Message,
    PatternMessage,
    Text,
    VariableRef,
    resourceFromFluent,
)


class TestFluentParser(unittest.TestCase):
    def test_simple_message(self):
        src = "a = A"
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [Message(("a",), PatternMessage([Text("A")]), (0, 5))],
        )

    def test_complex_message(self):
        src = "abc = A { $arg } B { msg } C"
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
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
                            FunctionRef("MESSAGE", Literal(False, "msg")),
                            Text(" C"),
                        ]
                    ),
                    res[0].span,
                )
            ],
        )

    def test_multiline_message(self):
        src = """\
abc =
    A
    B
    C
"""
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [Message(("abc",), PatternMessage([Text("A\nB\nC")]), res[0].span)],
        )

    def test_message_with_attribute(self):
        src = """\


abc = ABC
    .attr = Attr
"""
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [
                Message(("abc",), PatternMessage([Text("ABC")]), (2, 11)),
                Message(("abc", "attr"), PatternMessage([Text("Attr")]), (16, 28)),
            ],
        )

    def test_message_with_attribute_and_no_value(self):
        src = """\
abc =
    .attr = Attr
"""
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [
                Message(("abc", "attr"), PatternMessage([Text("Attr")]), (10, 22)),
            ],
        )

    def test_non_localizable(self):
        src = """\
### Resource Comment

foo = Foo

## Group Comment

-bar = Bar

##

# Standalone Comment

# Baz Comment
baz = Baz
"""
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [
                Comment(res[0].span),
                Message(("foo",), PatternMessage([Text("Foo")]), res[1].span),
                Comment(res[2].span),
                Message(("-bar",), PatternMessage([Text("Bar")]), res[3].span),
                Comment(res[4].span),
                Comment(res[5].span),
                Message(
                    ("baz",),
                    PatternMessage([Text("Baz")]),
                    res[6].span,
                    comment=res[6].comment,
                ),
            ],
        )
        c = res[0].span
        self.assertEqual(src[c[0] : c[1]], "### Resource Comment")
        c = res[2].span
        self.assertEqual(src[c[0] : c[1]], "## Group Comment")
        c = res[4].span
        self.assertEqual(src[c[0] : c[1]], "##")
        c = res[5].span
        self.assertEqual(src[c[0] : c[1]], "# Standalone Comment")
        c = res[6].comment
        self.assertEqual(src[c[0] : c[1]], "# Baz Comment")

    def test_junk(self):
        src = """\
# Comment

Line of junk

# Comment
msg = value
"""
        ast = FluentParser().parse(src)
        res = resourceFromFluent(ast)
        self.assertEqual(
            res,
            [
                Comment(res[0].span),
                Junk(res[1].span),
                Message(
                    ("msg",),
                    PatternMessage([Text("value")]),
                    res[2].span,
                    comment=res[2].comment,
                ),
            ],
        )
        c = res[0].span
        self.assertEqual(src[c[0] : c[1]], "# Comment")
        c = res[1].span
        self.assertEqual(src[c[0] : c[1]], "Line of junk\n\n")
        c = res[2].comment
        self.assertEqual(src[c[0] : c[1]], "# Comment")
