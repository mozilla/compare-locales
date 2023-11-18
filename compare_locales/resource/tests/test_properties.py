# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from ...parsers import PropertiesParser
from .. import (
    Message,
    ParseError,
    PatternMessage,
    Text,
    VariableRef,
    resourceFromProperties,
)


class TestPropertiesResource(unittest.TestCase):
    def test_backslashes(self):
        src = r"""one_line = This is one line
two_line = This is the first \
of two lines
one_line_trailing = This line ends in \\
two_lines_triple = This line is one of two and ends in \\\
and still has another line coming
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(
                    ("one_line",), PatternMessage([Text("This is one line")]), (0, 27)
                ),
                Message(
                    ("two_line",),
                    PatternMessage([Text("This is the first of two lines")]),
                    (28, 71),
                ),
                Message(
                    ("one_line_trailing",),
                    PatternMessage([Text("This line ends in \\")]),
                    (72, 112),
                ),
                Message(
                    ("two_lines_triple",),
                    PatternMessage(
                        [
                            Text(
                                "This line is one of two and ends in \\and still has another line coming"
                            )
                        ]
                    ),
                    (126, 218),
                ),
            ],
        )

    def test_printf_variables(self):
        src = r"""one = This %s is a string
two = This %(foo)d is a number
three = This %1$s and %2$d
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(
                    ("one",),
                    PatternMessage(
                        [Text("This "), VariableRef("%s"), Text(" is a string")]
                    ),
                    (0, 0),
                ),
                Message(
                    ("two",),
                    PatternMessage(
                        [Text("This "), VariableRef("%(foo)d"), Text(" is a number")]
                    ),
                    (0, 0),
                ),
                Message(
                    ("three",),
                    PatternMessage(
                        [
                            Text("This "),
                            VariableRef("%1$s"),
                            Text(" and "),
                            VariableRef("%2$d"),
                        ]
                    ),
                    (0, 0),
                ),
            ],
        )

    def test_license_header(self):
        src = """\
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

foo=value
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(("foo",), PatternMessage([Text("value")]), (200, 209)),
            ],
        )

    def test_escapes(self):
        src = rb"""
# unicode escapes
zero = some \unicode
one = \u0
two = \u41
three = \u042
four = \u0043
five = \u0044a
six = \a
seven = \n\r\t\\
"""
        parser = PropertiesParser()
        parser.readContents(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(
                    ("zero",),
                    PatternMessage([Text("some unicode")]),
                    comments=["unicode escapes"],
                ),
                Message(("one",), PatternMessage([Text(chr(0))])),
                Message(("two",), PatternMessage([Text("A")])),
                Message(("three",), PatternMessage([Text("B")])),
                Message(("four",), PatternMessage([Text("C")])),
                Message(("five",), PatternMessage([Text("Da")])),
                Message(("six",), PatternMessage([Text("a")])),
                Message(("seven",), PatternMessage([Text("\n\r\t\\")])),
            ],
        )

    def test_trailing_comment(self):
        src = """first = string
second = string

#
#commented out
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(("first",), PatternMessage([Text("string")])),
                Message(("second",), PatternMessage([Text("string")])),
            ],
        )

    def test_empty(self):
        parser = PropertiesParser()
        for src in ["", "\n", "\n\n", " \n\n"]:
            parser.readUnicode(src)
            res = resourceFromProperties(parser.walk())
            self.assertEqual(res, [])

    def test_pre_comment(self):
        src = """\
# comment
one = string

# standalone

# glued
# lines
second = string
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        res = resourceFromProperties(parser.walk())
        self.assertEqual(
            res,
            [
                Message(
                    ("one",),
                    PatternMessage([Text("string")]),
                    comments=["comment"],
                ),
                Message(
                    ("second",),
                    PatternMessage([Text("string")]),
                    comments=["glued", "lines"],
                ),
            ],
        )

    def test_junk(self):
        src = r"""key = This is valid
and this is junk
"""
        parser = PropertiesParser()
        parser.readUnicode(src)
        try:
            resourceFromProperties(parser.walk())
            raise AssertionError("Expected parse error")
        except ParseError:
            pass
