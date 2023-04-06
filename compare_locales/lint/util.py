# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from typing import Callable, Optional, Set, Tuple

from .. import paths

ReferenceAndTests = Tuple[Optional[str], Optional[Set[str]]]


def default_reference_and_tests(path) -> Tuple[None, None]:
    return None, None


def mirror_reference_and_tests(
    files: paths.ProjectFiles, basedir: str
) -> Callable[[str], ReferenceAndTests]:
    """Get reference files to check for conflicts in android-l10n and friends."""

    def get_reference_and_tests(path: str):
        for matchers in files.matchers:
            if "reference" not in matchers:
                continue
            matcher = matchers["reference"]
            if matcher.match(path) is None:
                continue
            ref_matcher = paths.Matcher(matcher, root=basedir)
            ref_path = matcher.sub(ref_matcher, path)
            return ref_path, matchers.get("test")
        return None, None

    return get_reference_and_tests


def l10n_base_reference_and_tests(
    files: paths.ProjectFiles,
) -> Callable[[str], ReferenceAndTests]:
    """Get reference files to check for conflicts in gecko-strings and friends."""

    def get_reference_and_tests(path: str):
        match = files.match(path)
        if match is None:
            return None, None
        ref, _, _, extra_tests = match
        return ref, extra_tests

    return get_reference_and_tests
