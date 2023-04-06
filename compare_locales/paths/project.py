# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Callable,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Union,
    cast,
)
from typing_extensions import NotRequired, TypedDict

from .. import mozpath
from .matcher import Matcher

if TYPE_CHECKING:
    from . import File


class ExcludeError(ValueError):
    pass


class PathDictionary(TypedDict):
    l10n: str
    locales: NotRequired[Sequence[str]]
    # merge: NotRequired[Matcher]
    module: NotRequired[str]
    reference: NotRequired[str]
    test: NotRequired[Set[str]]


class ProjectConfigPath(TypedDict):
    l10n: Matcher[str]
    locales: NotRequired[Sequence[str]]
    merge: NotRequired[Matcher[str]]
    module: Optional[str]
    reference: NotRequired[Matcher[str]]
    test: NotRequired[Set[str]]


FilterAction = Literal["error", "warning", "ignore"]


class FilterRule(TypedDict):
    action: FilterAction
    path: Union[str, List[str], Matcher[str]]
    key: NotRequired[Union[str, Sequence[str]]]


class CompiledFilterRule(TypedDict):
    action: FilterAction
    path: Matcher[str]
    key: NotRequired[re.Pattern[str]]


class ProjectConfig:
    """Abstraction of l10n project configuration data."""

    def __init__(self, path: Optional[str]) -> None:
        self.filter_py = None  # legacy filter code
        # {
        #  'l10n': pattern,
        #  'reference': pattern,  # optional
        #  'locales': [],  # optional
        #  'test': [],  # optional
        # }
        self.path = path
        self.root: Optional[str] = None
        self.paths: List[ProjectConfigPath] = []
        self.rules: List[CompiledFilterRule] = []
        self.locales: Optional[List[str]] = None
        # cache for all_locales, as that's not in `filter`
        self._all_locales: Optional[List[str]] = None
        self.environ = {}
        self.children: List[ProjectConfig] = []
        self.excludes: List[ProjectConfig] = []
        self._cache: Optional[ProjectConfig.FilterCache] = None

    def same(self, other: ProjectConfig) -> bool:
        """Equality test, ignoring locales."""
        if other.__class__ is not self.__class__:
            return False
        if len(self.children) != len(other.children):
            return False
        for prop in ("path", "root", "paths", "rules", "environ"):
            if getattr(self, prop) != getattr(other, prop):
                return False
        for this_child, other_child in zip(self.children, other.children):
            if not this_child.same(other_child):
                return False
        return True

    def set_root(self, basepath: str) -> None:
        if self.path is None:
            self.root = None
            return
        self.root = mozpath.abspath(mozpath.join(mozpath.dirname(self.path), basepath))

    def add_environment(self, **kwargs) -> None:
        self.environ.update(kwargs)

    def add_paths(self, *paths: PathDictionary) -> None:
        """Add path dictionaries to this config.
        The dictionaries must have a `l10n` key. For monolingual files,
        `reference` is also required.
        An optional key `test` is allowed to enable additional tests for this
        path pattern.
        """
        self._all_locales = None  # clear cache
        for d in paths:
            rv: ProjectConfigPath = {
                "l10n": Matcher(d["l10n"], env=self.environ, root=self.root),
                "module": d.get("module"),
            }
            if "reference" in d:
                rv["reference"] = Matcher(
                    d["reference"], env=self.environ, root=self.root
                )
            if "test" in d:
                rv["test"] = d["test"]
            if "locales" in d:
                rv["locales"] = d["locales"][:]
            self.paths.append(rv)

    def set_filter_py(self, filter_function: Callable) -> None:
        """Set legacy filter.py code.
        Assert that no rules are set.
        Also, normalize output already here.
        """
        assert not self.rules

        def filter_(
            module: Optional[str], path: str, entity: Optional[str] = None
        ) -> FilterAction:
            try:
                rv = filter_function(module, path, entity=entity)
            except BaseException:  # we really want to handle EVERYTHING here
                return "error"
            rv = {True: "error", False: "ignore", "report": "warning"}.get(rv, rv)
            assert rv in ("error", "ignore", "warning", None)
            return rv

        self.filter_py = filter_

    def add_rules(self, *rules) -> None:
        """Add rules to filter on.
        Assert that there's no legacy filter.py code hooked up.
        """
        assert self.filter_py is None
        for rule in rules:
            self.rules.extend(self._compile_rule(rule))

    def add_child(self, child: ProjectConfig) -> None:
        self._all_locales = None  # clear cache
        if child.excludes:
            raise ExcludeError("Included configs cannot declare their own excludes.")
        self.children.append(child)

    def exclude(self, child: ProjectConfig) -> None:
        for config in child.configs:
            if config.excludes:
                raise ExcludeError(
                    "Excluded configs cannot declare their own excludes."
                )
        self.excludes.append(child)

    def set_locales(self, locales: List[str], deep: bool = False) -> None:
        self._all_locales = None  # clear cache
        self.locales = locales
        if not deep:
            return
        for child in self.children:
            child.set_locales(locales, deep=deep)

    @property
    def configs(self) -> Iterator[ProjectConfig]:
        "Recursively get all configs in this project and its children"
        yield self
        for child in self.children:
            yield from child.configs

    @property
    def all_locales(self) -> List[str]:
        "Recursively get all locales in this project and its paths"
        if self._all_locales is None:
            all_locales: Set[str] = set()
            for config in self.configs:
                if config.locales is not None:
                    all_locales.update(config.locales)
                for paths in config.paths:
                    if "locales" in paths:
                        all_locales.update(paths["locales"])
            self._all_locales = sorted(all_locales)
        return self._all_locales

    def filter(self, l10n_file: File, entity: Optional[str] = None) -> FilterAction:
        """Filter a localization file or entities within, according to
        this configuration file."""
        if l10n_file.locale not in self.all_locales:
            return "ignore"
        if self.filter_py is not None:
            return self.filter_py(l10n_file.module, l10n_file.file, entity=entity)
        rv = self._filter(l10n_file, entity=entity)
        if rv is None:
            return "ignore"
        return rv

    class FilterCache:
        def __init__(self, locale: str) -> None:
            self.locale = locale
            self.rules: List[CompiledFilterRule] = []
            self.l10n_paths: List[Matcher] = []

    def cache(self, locale: str) -> ProjectConfig.FilterCache:
        if self._cache and self._cache.locale == locale:
            return self._cache
        self._cache = self.FilterCache(locale)
        for paths in self.paths:
            if "locales" in paths and locale not in paths["locales"]:
                continue
            self._cache.l10n_paths.append(paths["l10n"].with_env({"locale": locale}))
        for rule in self.rules:
            cached_rule = rule.copy()
            cached_rule["path"] = rule["path"].with_env({"locale": locale})
            self._cache.rules.append(cached_rule)
        return self._cache

    def _filter(
        self, l10n_file: File, entity: Optional[str] = None
    ) -> Optional[FilterAction]:
        if any(exclude.filter(l10n_file) == "error" for exclude in self.excludes):
            return
        actions = {child._filter(l10n_file, entity=entity) for child in self.children}
        if "error" in actions:
            # return early if we know we'll error
            return "error"

        cached = self.cache(cast(str, l10n_file.locale))
        if any(p.match(l10n_file.fullpath) for p in cached.l10n_paths):
            action = "error"
            for rule in reversed(cached.rules):
                if not rule["path"].match(l10n_file.fullpath):
                    continue
                if "key" in rule:
                    if entity is None or not rule["key"].match(entity):
                        continue
                elif entity is not None:
                    # key/file mismatch, not a matching rule
                    continue
                action = rule["action"]
                break
            actions.add(action)
        if "error" in actions:
            return "error"
        if "warning" in actions:
            return "warning"
        if "ignore" in actions:
            return "ignore"

    def _compile_rule(self, rule: FilterRule) -> Iterator[CompiledFilterRule]:
        assert "path" in rule
        if isinstance(rule["path"], list):
            for path in rule["path"]:
                rule_ = rule.copy()
                rule_["path"] = Matcher(path, env=self.environ, root=self.root)
                yield from self._compile_rule(rule_)
            return
        if isinstance(rule["path"], str):
            rule["path"] = Matcher(rule["path"], env=self.environ, root=self.root)

        if "key" not in rule:
            yield cast(CompiledFilterRule, rule)
            return
        key = rule["key"]
        if not isinstance(key, str):
            for key_ in key:
                rule_ = rule.copy()
                rule_["key"] = key_
                yield from self._compile_rule(rule_)
            return
        cr = cast(CompiledFilterRule, rule.copy())
        if key.startswith("re:"):
            key = key[3:]
        else:
            key = re.escape(key) + "$"
        cr["key"] = re.compile(key)
        yield cr
