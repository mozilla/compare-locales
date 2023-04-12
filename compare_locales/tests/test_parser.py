# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pkg_resources
import shutil
import tempfile
import unittest
from os.path import join

from compare_locales.parser import getParser, patchParser
from compare_locales.parsers import Parser


class TestEmptyParser(unittest.TestCase):
    def test_empty_parser(self):
        p = patchParser(Parser())
        entities = p.parse()
        self.assertTupleEqual(entities, tuple())


class TestUniversalNewlines(unittest.TestCase):
    def setUp(self):
        """Create a parser for this test."""
        self.parser = patchParser(Parser())
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        "tear down this test"
        del self.parser
        shutil.rmtree(self.dir)

    def test_universal_newlines(self):
        f = join(self.dir, "file")
        with open(f, "wb") as fh:
            fh.write(b"one\ntwo\rthree\r\n")
        self.parser.readFile(f)
        self.assertEqual(self.parser.ctx.contents, "one\ntwo\nthree\n")


class TestPlugins(unittest.TestCase):
    def setUp(self):
        self.old_working_set_state = pkg_resources.working_set.__getstate__()
        distribution = pkg_resources.Distribution(__file__)
        entry_point = pkg_resources.EntryPoint.parse(
            "test_parser = compare_locales.tests.test_parser:DummyParser",
            dist=distribution,
        )
        distribution._ep_map = {"compare_locales.parsers": {"test_parser": entry_point}}
        pkg_resources.working_set.add(distribution)

    def tearDown(self):
        pkg_resources.working_set.__setstate__(self.old_working_set_state)

    def test_dummy_parser(self):
        p = getParser("some/weird/file.ext")
        self.assertIsInstance(p, DummyParser)


class DummyParser(Parser):
    def use(self, path):
        return path.endswith("weird/file.ext")
