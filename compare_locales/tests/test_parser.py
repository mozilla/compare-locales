# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from importlib.metadata import EntryPoint
import shutil
import tempfile
import textwrap
import unittest
from unittest import mock

from compare_locales import parser, mozpath


class TestParserContext(unittest.TestCase):
    def test_linecol(self):
        "Should return 1-based line and column numbers."
        ctx = parser.Parser.Context("""first line
second line
third line
""")
        self.assertEqual(ctx.linecol(0), (1, 1))
        self.assertEqual(ctx.linecol(1), (1, 2))
        self.assertEqual(ctx.linecol(len("first line")), (1, len("first line") + 1))
        self.assertEqual(ctx.linecol(len("first line") + 1), (2, 1))
        self.assertEqual(ctx.linecol(len(ctx.contents)), (4, 1))

    def test_empty_parser(self):
        p = parser.Parser()
        entities = p.parse()
        self.assertTupleEqual(entities, tuple())


class TestOffsetComment(unittest.TestCase):
    def test_offset(self):
        ctx = parser.Parser.Context(textwrap.dedent("""\
            #foo
            #bar
            # baz
            """))  # noqa
        offset_comment = parser.OffsetComment(ctx, (0, len(ctx.contents)))
        self.assertEqual(
            offset_comment.val,
            textwrap.dedent("""\
                foo
                bar
                 baz
            """),
        )


class TestUniversalNewlines(unittest.TestCase):
    def setUp(self):
        """Create a parser for this test."""
        self.parser = parser.Parser()
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        "tear down this test"
        del self.parser
        shutil.rmtree(self.dir)

    def test_universal_newlines(self):
        f = mozpath.join(self.dir, "file")
        with open(f, "wb") as fh:
            fh.write(b"one\ntwo\rthree\r\n")
        self.parser.readFile(f)
        self.assertEqual(self.parser.ctx.contents, "one\ntwo\nthree\n")


class TestPlugins(unittest.TestCase):
    def setUp(self):
        entry_point = EntryPoint(
            name="test_parser",
            value="compare_locales.tests.test_parser:DummyParser",
            group="compare_locales.parsers",
        )
        # Returning a dict exercises the non-selectable code path in
        # getParser, which works regardless of the Python version.
        self.patcher = mock.patch(
            "importlib.metadata.entry_points",
            return_value={"compare_locales.parsers": [entry_point]},
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_dummy_parser(self):
        p = parser.getParser("some/weird/file.ext")
        self.assertIsInstance(p, DummyParser)


class DummyParser(parser.Parser):
    def use(self, path):
        return path.endswith("weird/file.ext")
