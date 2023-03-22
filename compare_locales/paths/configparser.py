# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations
import errno
import logging
from compare_locales import mozpath
from .project import ProjectConfig
from .matcher import expand
import toml
from typing import TYPE_CHECKING, Dict, Iterator, Optional

if TYPE_CHECKING:
    from compare_locales.paths.project import ProjectConfig


class ConfigNotFound(EnvironmentError):
    def __init__(self, path):
        super().__init__(errno.ENOENT, "Configuration file not found", path)


class ParseContext:
    def __init__(
        self, path: str, env: Dict[str, str], ignore_missing_includes: bool
    ) -> None:
        self.path = path
        self.env = env
        self.ignore_missing_includes = ignore_missing_includes
        self.data = None
        self.pc = ProjectConfig(path)


class TOMLParser:
    def parse(
        self,
        path: str,
        env: Optional[Dict[str, str]] = None,
        ignore_missing_includes: bool = False,
    ) -> ProjectConfig:
        ctx = self.context(
            path, env=env, ignore_missing_includes=ignore_missing_includes
        )
        self.load(ctx)
        self.processBasePath(ctx)
        self.processEnv(ctx)
        self.processPaths(ctx)
        self.processFilters(ctx)
        self.processIncludes(ctx)
        self.processExcludes(ctx)
        self.processLocales(ctx)
        return self.asConfig(ctx)

    def context(
        self,
        path: str,
        env: Optional[Dict[str, str]] = None,
        ignore_missing_includes: bool = False,
    ) -> ParseContext:
        return ParseContext(
            path,
            env if env is not None else {},
            ignore_missing_includes,
        )

    def load(self, ctx: ParseContext) -> None:
        try:
            with open(ctx.path) as fin:
                ctx.data = toml.load(fin)
        except (toml.TomlDecodeError, OSError):
            raise ConfigNotFound(ctx.path)

    def processBasePath(self, ctx: ParseContext) -> None:
        assert ctx.data is not None
        ctx.pc.set_root(ctx.data.get("basepath", "."))

    def processEnv(self, ctx: ParseContext) -> None:
        assert ctx.data is not None
        ctx.pc.add_environment(**ctx.data.get("env", {}))
        # add parser environment, possibly overwriting file variables
        ctx.pc.add_environment(**ctx.env)

    def processLocales(self, ctx: ParseContext) -> None:
        assert ctx.data is not None
        if "locales" in ctx.data:
            ctx.pc.set_locales(ctx.data["locales"])

    def processPaths(self, ctx: ParseContext) -> None:
        assert ctx.data is not None
        for data in ctx.data.get("paths", []):
            paths = {"l10n": data["l10n"]}
            if "locales" in data:
                paths["locales"] = data["locales"]
            if "reference" in data:
                paths["reference"] = data["reference"]
            if "test" in data:
                paths["test"] = data["test"]
            ctx.pc.add_paths(paths)

    def processFilters(self, ctx: ParseContext) -> None:
        assert ctx.data is not None
        for data in ctx.data.get("filters", []):
            paths = data["path"]
            if isinstance(paths, str):
                paths = [paths]
            rule = {"path": paths, "action": data["action"]}
            if "key" in data:
                rule["key"] = data["key"]
            ctx.pc.add_rules(rule)

    def processIncludes(self, ctx: ParseContext) -> None:
        for child in self._processChild(ctx, "includes"):
            ctx.pc.add_child(child)

    def processExcludes(self, ctx: ParseContext) -> None:
        for child in self._processChild(ctx, "excludes"):
            ctx.pc.exclude(child)

    def _processChild(self, ctx: ParseContext, field: str) -> Iterator[ProjectConfig]:
        assert ctx.data is not None
        if field not in ctx.data:
            return
        for child_config in ctx.data[field]:
            # resolve child_config['path'] against our root and env
            p = mozpath.normpath(
                expand(ctx.pc.root, child_config["path"], ctx.pc.environ)
            )
            try:
                child = self.parse(
                    p, env=ctx.env, ignore_missing_includes=ctx.ignore_missing_includes
                )
            except ConfigNotFound as e:
                if not ctx.ignore_missing_includes:
                    raise
                (
                    logging.getLogger("compare-locales.io").error(
                        "%s: %s", e.strerror, e.filename
                    )
                )
                continue
            yield child

    def asConfig(self, ctx: ParseContext) -> ProjectConfig:
        return ctx.pc
