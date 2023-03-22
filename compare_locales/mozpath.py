# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Like :py:mod:`os.path`, with a reduced set of functions, and with normalized
path separators (always use forward slashes).
Also contains a few additional utilities not found in :py:mod:`os.path`.
"""
from __future__ import annotations

import os
import posixpath
import re
from typing import List, Tuple


def normsep(path: str) -> str:
    """
    Normalize path separators, by using forward slashes instead of whatever
    :py:const:`os.sep` is.
    """
    if os.sep != "/":
        path = path.replace(os.sep, "/")
    if os.altsep and os.altsep != "/":
        path = path.replace(os.altsep, "/")
    return path


def relpath(path: str, start: str) -> str:
    rel = normsep(os.path.relpath(path, start))
    return "" if rel == "." else rel


def realpath(path: str) -> str:
    return normsep(os.path.realpath(path))


def abspath(path: str) -> str:
    return normsep(os.path.abspath(path))


def join(*paths) -> str:
    return normsep(os.path.join(*paths))


def normpath(path: str) -> str:
    return posixpath.normpath(normsep(path))


def dirname(path: str) -> str:
    return posixpath.dirname(normsep(path))


def commonprefix(paths: List[str]) -> str:
    return posixpath.commonprefix([normsep(path) for path in paths])


def basename(path: str) -> str:
    return os.path.basename(path)


def splitext(path: str) -> Tuple[str, str]:
    return posixpath.splitext(normsep(path))


def split(path: str) -> List[str]:
    """
    Return the normalized path as a list of its components.

        ``split('foo/bar/baz')`` returns ``['foo', 'bar', 'baz']``
    """
    return normsep(path).split("/")


def basedir(path: str, bases: List[str]) -> str:
    """
    Given a list of directories (`bases`), return which one contains the given
    path. If several matches are found, the deepest base directory is returned.

    ``basedir('foo/bar/baz', ['foo', 'baz', 'foo/bar'])`` returns ``'foo/bar'``
    (`'foo'` and `'foo/bar'` both match, but `'foo/bar'` is the deepest match)
    """
    path = normsep(path)
    bases = [normsep(b) for b in bases]
    if path in bases:
        return path
    for b in sorted(bases, reverse=True):
        if b == "" or path.startswith(b + "/"):
            return b


re_cache = {}


def match(path: str, pattern: str) -> bool:
    """
    Return whether the given path matches the given pattern.
    An asterisk can be used to match any string, including the null string, in
    one part of the path:

        ``foo`` matches ``*``, ``f*`` or ``fo*o``

    However, an asterisk matching a subdirectory may not match the null string:

        ``foo/bar`` does *not* match ``foo/*/bar``

    If the pattern matches one of the ancestor directories of the path, the
    patch is considered matching:

        ``foo/bar`` matches ``foo``

    Two adjacent asterisks can be used to match files and zero or more
    directories and subdirectories.

        ``foo/bar`` matches ``foo/**/bar``, or ``**/bar``
    """
    if not pattern:
        return True
    if pattern not in re_cache:
        last_end = 0
        p = ""
        for m in re.finditer(r"(?:(^|/)\*\*(/|$))|(?P<star>\*)", pattern):
            if m.start() > last_end:
                p += re.escape(pattern[last_end : m.start()])
            if m.group("star"):
                p += "[^/]*"
            elif m.group(2):
                p += re.escape(m.group(1)) + r"(?:.+%s)?" % m.group(2)
            else:
                p += r"(?:%s.+)?" % re.escape(m.group(1))
            last_end = m.end()
        p += re.escape(pattern[last_end:]) + "(?:/.*)?$"
        re_cache[pattern] = re.compile(p)
    return re_cache[pattern].match(path) is not None


def rebase(oldbase: str, base: str, relativepath: str) -> str:
    """
    Return `relativepath` relative to `base` instead of `oldbase`.
    """
    if base == oldbase:
        return relativepath
    if len(base) < len(oldbase):
        assert basedir(oldbase, [base]) == base
        relbase = relpath(oldbase, base)
        result = join(relbase, relativepath)
    else:
        assert basedir(base, [oldbase]) == oldbase
        relbase = relpath(base, oldbase)
        result = relpath(relativepath, relbase)
    result = normpath(result)
    if relativepath.endswith("/") and not result.endswith("/"):
        result += "/"
    return result
