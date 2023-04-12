# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from compare_locales.tests import BaseHelper
from compare_locales.paths import File


class TestChecks(BaseHelper):
    file = File("foo.ini", "foo.ini")
    refContent = b"""\
[Strings]
foo=good
"""

    def test_ok(self):
        self._test(b"[Strings]\nfoo=other", tuple())

    def test_bad_encoding(self):
        self._test(
            "foo=touché".encode("latin-1"),
            (("warning", 9, "\ufffd in: foo", "encodings"),),
        )
