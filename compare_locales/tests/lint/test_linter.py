# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

from compare_locales.lint import linter
from compare_locales.parser import base as parser


class MockChecker:
    def __init__(self, mocked):
        self.results = mocked

    def check(self, ent, ref):
        yield from self.results


class EntityTest(unittest.TestCase):
    def test_junk(self):
        el = linter.EntityLinter([], None, {})
        ctx = parser.Parser.Context("foo\nbar\n")
        ent = parser.Junk(ctx, (4, 7))
        res = el.handle_junk(ent)
        self.assertIsNotNone(res)
        self.assertEqual(res["lineno"], 2)
        self.assertEqual(res["column"], 1)
        ent = parser.LiteralEntity("one", "two", "one = two")
        self.assertIsNone(el.handle_junk(ent))

    def test_full_entity(self):
        ctx = parser.Parser.Context("""\
one = two
two = three
one = four
""")
        entities = [
            parser.Entity(ctx, None, None, (0, 10), (0, 3), (6, 9)),
            parser.Entity(ctx, None, None, (10, 22), (10, 13), (16, 21)),
            parser.Entity(ctx, None, None, (22, 33), (22, 25), (28, 32)),
        ]
        self.assertEqual(
            (entities[0].all, entities[0].key, entities[0].val),
            ("one = two\n", "one", "two"),
        )
        self.assertEqual(
            (entities[1].all, entities[1].key, entities[1].val),
            ("two = three\n", "two", "three"),
        )
        self.assertEqual(
            (entities[2].all, entities[2].key, entities[2].val),
            ("one = four\n", "one", "four"),
        )
        el = linter.EntityLinter(entities, None, {})
        results = list(el.lint_full_entity(entities[1]))
        self.assertListEqual(results, [])
        results = list(el.lint_full_entity(entities[2]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "error")
        self.assertEqual(result["lineno"], 3)
        self.assertEqual(result["column"], 1)
        # finally check for conflict
        el.reference = {"two": parser.LiteralEntity("two = other", "two", "other")}
        results = list(el.lint_full_entity(entities[1]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["lineno"], 2)
        self.assertEqual(result["column"], 1)

    def test_in_value(self):
        ctx = parser.Parser.Context("""\
one = two
""")
        entities = [
            parser.Entity(ctx, None, None, (0, 10), (0, 3), (6, 9)),
        ]
        self.assertEqual(
            (entities[0].all, entities[0].key, entities[0].val),
            ("one = two\n", "one", "two"),
        )
        checker = MockChecker(
            [
                ("error", 2, "Incompatible resource types", "android"),
            ]
        )
        el = linter.EntityLinter(entities, checker, {})
        results = list(el.lint_value(entities[0]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "error")
        self.assertEqual(result["lineno"], 1)
        self.assertEqual(result["column"], 9)


class FluentEntityTest(unittest.TestCase):
    """Lint reporting behavior for Fluent messages."""

    def _parse(self, source):
        from compare_locales import parser as cl_parser

        file_parser = cl_parser.getParser("foo.ftl")
        file_parser.readUnicode(source)
        return list(file_parser.parse())

    def _ref(self, source):
        return {e.key: e for e in self._parse(source)}

    def test_value_only_change(self):
        current = self._parse("# Comment\nmsg = new value\n")
        reference = self._ref("# Comment\nmsg = old value\n")
        el = linter.EntityLinter(current, None, reference)
        results = list(el.lint_full_entity(current[0]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "warning")
        # ID line, not the comment line above
        self.assertEqual(result["lineno"], 2)
        self.assertEqual(result["column"], 1)
        self.assertNotIn("lineoffset", result)

    def test_attribute_change(self):
        current = self._parse(
            "# Comment\nmsg = value\n    .label = new\n    .title = also new\n"
        )
        reference = self._ref(
            "# Comment\nmsg = value\n    .label = old\n    .title = also old\n"
        )
        el = linter.EntityLinter(current, None, reference)
        results = list(el.lint_full_entity(current[0]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "warning")
        # ID line
        self.assertEqual(result["lineno"], 2)
        self.assertEqual(result["column"], 1)
        # Spans both attribute lines (last attribute is line 4)
        self.assertEqual(result["lineoffset"], 2)

    def test_comment_only_change_no_warning(self):
        current = self._parse("# New comment\nmsg = value\n")
        reference = self._ref("# Old comment\nmsg = value\n")
        el = linter.EntityLinter(current, None, reference)
        results = list(el.lint_full_entity(current[0]))
        self.assertEqual(results, [])

    def test_duplicate_id_reports_at_id_line(self):
        current = self._parse("# Comment\nmsg = one\nmsg = two\n")
        el = linter.EntityLinter(current, None, {})
        results = list(el.lint_full_entity(current[1]))
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["level"], "error")
        # Second definition is on line 3
        self.assertEqual(result["lineno"], 3)
        self.assertEqual(result["column"], 1)
