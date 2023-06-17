# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from ...parsers import PropertiesParser
from .. import Comment, Junk, Message, PatternMessage, Text, resourceFromProperties


class TestPropertiesResource(unittest.TestCase):
    def test_backslashes(self):
        src = r"""one_line = This is one line
two_line = This is the first \
of two lines
one_line_trailing = This line ends in \\
and has junk
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
                Junk((113, 126)),
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
                Comment((0, 198)),
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
                    span=(19, 39),
                    comment=(1, 18),
                ),
                Message(("one",), PatternMessage([Text(chr(0))]), res[1].span),
                Message(("two",), PatternMessage([Text("A")]), res[2].span),
                Message(("three",), PatternMessage([Text("B")]), res[3].span),
                Message(("four",), PatternMessage([Text("C")]), res[4].span),
                Message(("five",), PatternMessage([Text("Da")]), res[5].span),
                Message(("six",), PatternMessage([Text("a")]), res[6].span),
                Message(("seven",), PatternMessage([Text("\n\r\t\\")]), res[7].span),
            ],
        )
        start, end = res[0].comment
        self.assertEqual(src[start:end], b"# unicode escapes")

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
                Message(("first",), PatternMessage([Text("string")]), res[0].span),
                Message(("second",), PatternMessage([Text("string")]), res[1].span),
                Comment(res[2].span),
            ],
        )
        start, end = res[2].span
        self.assertEqual(src[start:end], "#\n#commented out")

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
                    span=(10, 22),
                    comment=(0, 9),
                ),
                Comment(res[1].span),
                Message(
                    ("second",),
                    PatternMessage([Text("string")]),
                    res[2].span,
                    comment=res[2].comment,
                ),
            ],
        )
        c0 = res[0].comment
        self.assertEqual(src[c0[0] : c0[1]], "# comment")
        c1 = res[1].span
        self.assertEqual(src[c1[0] : c1[1]], "# standalone")
        c2 = res[2].comment
        self.assertEqual(src[c2[0] : c2[1]], "# glued")
