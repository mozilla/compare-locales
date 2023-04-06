# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import itertools
import os
import re
from typing import (
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
    cast,
    overload,
)

from .. import mozpath

# Android uses non-standard locale codes, these are the mappings
# back and forth
ANDROID_LEGACY_MAP = {"he": "iw", "id": "in", "yi": "ji"}
ANDROID_STANDARD_MAP = {
    legacy: standard for standard, legacy in ANDROID_LEGACY_MAP.items()
}

StrType = TypeVar("StrType", str, bytes)


class Matcher(Generic[StrType]):
    """Path pattern matcher
    Supports path matching similar to mozpath.match(), but does
    not match trailing file paths without trailing wildcards.
    Also gets a prefix, which is the path before the first wildcard,
    which is good for filesystem iterations, and allows to replace
    the own matches in a path on a different Matcher. compare-locales
    uses that to transform l10n and en-US paths back and forth.
    """

    env: EnvType

    @overload
    def __new__(cls, other: Matcher[StrType]) -> Matcher[StrType]:
        ...

    @overload
    def __new__(
        cls,
        pattern: Union[str, Matcher],
        env: Dict[str, str] = {},
        root: Optional[str] = None,
        encoding: None = None,
    ) -> Matcher[str]:
        ...

    @overload
    def __new__(
        cls,
        pattern: Union[str, Matcher],
        env: Dict[str, str] = {},
        root: Optional[str] = None,
        encoding: Optional[str] = None,
    ) -> Matcher[bytes]:
        ...

    def __new__(
        cls, *args, **kwargs
    ) -> Union[Matcher[str], Matcher[bytes], Matcher[StrType]]:
        return super().__new__(cls)  # type: ignore

    def __init__(
        self,
        pattern_or_other: Union[str, Matcher],
        env: Dict[str, str] = {},
        root: Optional[str] = None,
        encoding: Optional[str] = None,
    ) -> None:
        """Create regular expression similar to mozpath.match()."""
        parser = PatternParser()
        real_env: EnvType = {k: parser.parse(v) for k, v in env.items()}
        self._cached_re = None
        if root is not None:
            # make sure that our root is fully expanded and ends with /
            root = mozpath.abspath(root) + "/"
        # allow constructing Matchers from Matchers
        if isinstance(pattern_or_other, Matcher):
            other = pattern_or_other
            self.pattern = Pattern(other.pattern)
            self.env = other.env.copy()
            self.env.update(real_env)
            if root is not None:
                self.pattern.root = root
            self.encoding = other.encoding
            return
        self.env = real_env
        pattern = pattern_or_other
        self.pattern = parser.parse(pattern)
        if root is not None:
            self.pattern.root = root
        self.encoding = encoding

    def with_env(self, environ: Dict[str, str]) -> Matcher[str]:
        return Matcher(self, environ)

    @property
    def prefix(self) -> StrType:
        subpattern = Pattern(self.pattern[: self.pattern.prefix_length])
        subpattern.root = self.pattern.root
        prefix = subpattern.expand(self.env)
        if self.encoding is not None:
            prefix = prefix.encode(self.encoding)
        return cast(StrType, prefix)

    def match(self, path: StrType) -> Union[Dict[str, str], None]:
        """Test the given path against this matcher and its environment.

        Return None if there's no match, and the dictionary of matched
        variables in this matcher if there's a match.
        """
        m = self._cached_regex().match(path)  # type: ignore
        if m is None:
            return None
        d = cast(Dict[str, str], m.groupdict())
        if self.encoding is not None:
            d = {
                key: cast(bytes, value).decode(self.encoding)
                for key, value in d.items()
            }
        if "android_locale" in d and "locale" not in d:
            # map android_locale to locale code
            locale = d["android_locale"]
            # map legacy locale codes, he <-> iw, id <-> in, yi <-> ji
            locale = re.sub(
                r"(iw|in|ji)(?=\Z|-)",
                lambda legacy: ANDROID_STANDARD_MAP[legacy.group(1)],
                locale,
            )
            locale = re.sub(r"-r([A-Z]{2})", r"-\1", locale)
            locale = locale.replace("b+", "").replace("+", "-")
            d["locale"] = locale
        return d

    _cached_re: Union[re.Pattern[StrType], None]

    def _cached_regex(self) -> re.Pattern[StrType]:
        if self._cached_re is None:
            pattern = self.pattern.regex_pattern(self.env) + "$"
            if self.encoding is not None:
                pattern = pattern.encode(self.encoding)
                self._cached_re = re.compile(pattern)  # type: ignore
            self._cached_re = re.compile(pattern)  # type: ignore
        return self._cached_re

    def sub(self, other: Matcher, path: StrType) -> Optional[StrType]:
        """
        Replace the wildcard matches in this pattern into the
        pattern of the other Match object.
        """
        m = self.match(path)
        if m is None:
            return None
        env = {}
        env.update(
            (key, Literal(value if value is not None else ""))
            for key, value in m.items()
        )
        env.update(other.env)
        path_ = other.pattern.expand(env)
        if self.encoding is not None:
            path_ = path_.encode(self.encoding)
        return cast(StrType, path_)

    def concat(self, other: Union[str, Matcher]) -> Matcher:
        """Concat two Matcher objects.

        The intent is to create one Matcher with variable substitutions that
        behaves as if you joined the resulting paths.
        This doesn't do path separator logic, though, and it won't resolve
        parent directories.
        """
        other_matcher = other if isinstance(other, Matcher) else Matcher(other)
        other_pattern = other_matcher.pattern
        if other_pattern.root is not None:
            raise ValueError("Other matcher must not be rooted")
        result = Matcher(self)
        result.pattern += other_pattern
        if self.pattern.prefix_length == len(self.pattern):
            if result.pattern.prefix_length:
                if other_pattern.prefix_length:
                    result.pattern.prefix_length += other_pattern.prefix_length
            else:
                result.pattern.prefix_length = other_pattern.prefix_length
        result.env.update(other_matcher.env)
        return result

    def __str__(self) -> str:
        return self.pattern.expand(self.env)

    def __repr__(self):
        return "{}({!r}, env={!r}, root={!r})".format(
            type(self).__name__, self.pattern, self.env, self.pattern.root
        )

    def __ne__(self, other: Matcher) -> bool:
        return not (self == other)

    def __eq__(self, other: Matcher) -> bool:
        """Equality for Matcher.

        The equality for Matchers is defined to have the same pattern,
        and no conflicting environment. Additional environment settings
        in self or other are OK.
        """
        if other.__class__ is not self.__class__:
            return NotImplemented
        if self.pattern != other.pattern:
            return False
        if self.env and other.env:
            for k in self.env:
                if k not in other.env:
                    continue
                if self.env[k] != other.env[k]:
                    return False
        if self.encoding != other.encoding:
            return False
        return True


def expand(root: Optional[str], path: str, env: Dict[str, str]) -> str:
    """Expand a given path relative to the given root,
    using the given env to resolve variables.

    This will break if the path contains wildcards.
    """
    matcher = Matcher(path, env=env, root=root)
    return str(matcher)


class MissingEnvironment(Exception):
    pass


class Node:
    """Abstract base class for all nodes in parsed patterns."""

    def regex_pattern(self, env):
        """Create a regular expression fragment for this Node."""
        raise NotImplementedError

    def expand(self, env):
        """Convert this node to a string with the given environment."""
        raise NotImplementedError


class Pattern(list, Node):
    def __init__(
        self,
        iterable: Union[
            Pattern,
            List[Union[Literal, AndroidLocale]],
            List[Variable],
            List[Literal],
            List[Union[Variable, Literal]],
        ] = [],
    ) -> None:
        list.__init__(self, iterable)
        self.root = getattr(iterable, "root", None)
        self.prefix_length: Optional[int] = getattr(iterable, "prefix_length", None)

    def regex_pattern(self, env: EnvType) -> str:
        root = ""
        if self.root is not None:
            # make sure we're not hiding a full path
            first_seg = self[0].expand(env)
            if not os.path.isabs(first_seg):
                root = re.escape(self.root)
        return root + "".join(child.regex_pattern(env) for child in self)

    def expand(self, env: EnvType, raise_missing: bool = False) -> str:
        root = ""
        if self.root is not None:
            # make sure we're not hiding a full path
            first_seg = self[0].expand(env)
            if not os.path.isabs(first_seg):
                root = self.root
        return root + "".join(self._expand_children(env, raise_missing))

    def _expand_children(
        self, env: EnvType, raise_missing: bool
    ) -> Iterator[Union[str, Literal]]:
        # Helper iterator to convert Exception to a stopped iterator
        for child in self:
            try:
                yield child.expand(env, raise_missing=True)
            except MissingEnvironment:
                if raise_missing:
                    raise
                return

    def __ne__(self, other: "Pattern") -> bool:
        return not (self == other)

    def __eq__(self, other: Union[Pattern, List[str]]) -> bool:
        if not super().__eq__(other):
            return False
        if other.__class__ == list:
            # good for tests and debugging
            return True
        return (
            self.root == cast(Pattern, other).root
            and self.prefix_length == cast(Pattern, other).prefix_length
        )


class Literal(str, Node):
    def regex_pattern(self, env: EnvType) -> str:
        return re.escape(self)

    def expand(self, env: EnvType, raise_missing: bool = False) -> Literal:
        return self


class Variable(Node):
    def __init__(self, name: str, repeat: bool = False) -> None:
        self.name = name
        self.repeat = repeat

    def regex_pattern(self, env: EnvType) -> str:
        if self.repeat:
            return f"(?P={self.name})"
        return f"(?P<{self.name}>{self._pattern_from_env(env)})"

    def _pattern_from_env(self, env: EnvType) -> str:
        if self.name in env:
            # make sure we match the value in the environment
            return env[self.name].regex_pattern(self._no_cycle(env))
        # match anything, including path segments
        return ".+?"

    def expand(self, env: EnvType, raise_missing: bool = False) -> Union[str, Literal]:
        """Create a string for this Variable.

        This expansion happens recursively. We avoid recusion loops
        by removing the current variable from the environment that's used
        to expand child variable references.
        """
        if self.name not in env:
            raise MissingEnvironment
        return env[self.name].expand(self._no_cycle(env), raise_missing=raise_missing)

    def _no_cycle(self, env: EnvType) -> EnvType:
        """Remove our variable name from the environment.
        That way, we can't create cyclic references.
        """
        if self.name not in env:
            return env
        env = env.copy()
        env.pop(self.name)
        return env

    def __repr__(self):
        return f'Variable(name="{self.name}")'

    def __ne__(self, other):
        return not (self == other)

    def __eq__(self, other: "Variable") -> bool:
        if other.__class__ is not self.__class__:
            return False
        return self.name == other.name and self.repeat == other.repeat


class AndroidLocale(Variable):
    """Subclass for Android locale code mangling.

    Supports ab-rCD and b+ab+Scrip+DE.
    Language and Language-Region tags get mapped to ab-rCD, more complex
    Locale tags to b+.
    """

    def __init__(self, repeat: bool = False) -> None:
        self.name = "android_locale"
        self.repeat = repeat

    def _pattern_from_env(self, env: EnvType) -> str:
        android_locale = self._get_android_locale(env)
        if android_locale is not None:
            return re.escape(android_locale)
        return ".+?"

    def expand(self, env: EnvType, raise_missing: bool = False) -> str:
        """Create a string for this Variable.

        This expansion happens recursively. We avoid recusion loops
        by removing the current variable from the environment that's used
        to expand child variable references.
        """
        android_locale = self._get_android_locale(env)
        if android_locale is None:
            raise MissingEnvironment
        return android_locale

    def _get_android_locale(self, env: EnvType) -> Optional[str]:
        if "locale" not in env:
            return None
        android = bcp47 = env["locale"].expand(self._no_cycle(env))
        # map legacy locale codes, he <-> iw, id <-> in, yi <-> ji
        android = bcp47 = re.sub(
            r"(he|id|yi)(?=\Z|-)",
            lambda standard: ANDROID_LEGACY_MAP[standard.group(1)],
            bcp47,
        )
        if re.match(r"[a-z]{2,3}-[A-Z]{2}", bcp47):
            android = "{}-r{}".format(*bcp47.split("-"))
        elif "-" in bcp47:
            android = "b+" + bcp47.replace("-", "+")
        return android


class Star(Node):
    def __init__(self, number: int) -> None:
        self.number = number

    def regex_pattern(self, env: EnvType) -> str:
        return f"(?P<s{self.number}>[^/]*)"

    def expand(self, env: EnvType, raise_missing: bool = False) -> Literal:
        return cast(Literal, env["s%d" % self.number])

    def __repr__(self):
        return type(self).__name__

    def __ne__(self, other):
        return not (self == other)

    def __eq__(self, other: Star) -> bool:
        if other.__class__ is not self.__class__:
            return False
        return self.number == other.number


class Starstar(Star):
    def __init__(self, number: int, suffix: str) -> None:
        self.number = number
        self.suffix = suffix

    def regex_pattern(self, env: EnvType) -> str:
        return f"(?P<s{self.number}>.+{self.suffix})?"

    def __ne__(self, other):
        return not (self == other)

    def __eq__(self, other: Starstar) -> bool:
        if not super().__eq__(other):
            return False
        return self.suffix == other.suffix


PATH_SPECIAL = re.compile(
    r"(?P<starstar>(?<![^/}])\*\*(?P<suffix>/|$))"
    r"|"
    r"(?P<star>\*)"
    r"|"
    r"(?P<variable>{ *(?P<varname>[\w]+) *})"
)


class PatternParser:
    def __init__(self) -> None:
        # Not really initializing anything, just making room for our
        # result and state members.
        self.pattern = cast(Pattern, None)
        self._cursor = 0
        self._stargroup = cast(itertools.count, None)
        self._known_vars = cast(Set[str], None)

    def parse(self, pattern: str) -> Pattern:
        if isinstance(pattern, Pattern):
            return pattern
        if isinstance(pattern, Matcher):
            return pattern.pattern
        # Initializing result and state
        self.pattern = Pattern()
        self._stargroup = itertools.count(1)
        self._known_vars = set()
        self._cursor = 0
        for match in PATH_SPECIAL.finditer(pattern):
            if match.start() > self._cursor:
                self.pattern.append(Literal(pattern[self._cursor : match.start()]))
            self.handle(match)
        self.pattern.append(Literal(pattern[self._cursor :]))
        if self.pattern.prefix_length is None:
            self.pattern.prefix_length = len(self.pattern)
        return self.pattern

    def handle(self, match: re.Match[str]) -> None:
        if match.group("variable"):
            self.variable(match)
        else:
            self.wildcard(match)
        self._cursor = match.end()

    def variable(self, match: re.Match[str]) -> None:
        varname = match.group("varname")
        repeat = varname in self._known_vars
        # Special case Android locale code matching.
        # It's kinda sad, but true.
        self.pattern.append(
            AndroidLocale(repeat)
            if varname == "android_locale"
            else Variable(varname, repeat)
        )
        self._known_vars.add(varname)

    def wildcard(self, match: re.Match[str]) -> None:
        # wildcard found, stop prefix
        if self.pattern.prefix_length is None:
            self.pattern.prefix_length = len(self.pattern)
        wildcard = next(self._stargroup)
        if match.group("star"):
            # *
            self.pattern.append(Star(wildcard))
        else:
            # **
            self.pattern.append(Starstar(wildcard, match.group("suffix")))


EnvType = Dict[str, Union[Pattern, Literal]]
