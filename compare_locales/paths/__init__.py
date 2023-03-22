# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from typing import Optional, Union

from .. import mozpath
from .configparser import ConfigNotFound, TOMLParser
from .files import REFERENCE_LOCALE, ProjectFiles
from .ini import (
    EnumerateApp,
    EnumerateSourceTreeApp,
    L10nConfigParser,
    SourceTreeConfigParser,
)
from .matcher import Matcher
from .project import ProjectConfig

__all__ = [
    "Matcher",
    "ProjectConfig",
    "L10nConfigParser",
    "SourceTreeConfigParser",
    "EnumerateApp",
    "EnumerateSourceTreeApp",
    "ProjectFiles",
    "REFERENCE_LOCALE",
    "TOMLParser",
    "ConfigNotFound",
]


class File:
    def __init__(
        self,
        fullpath: str,
        file: str,
        module: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> None:
        self.fullpath = fullpath
        self.file = file
        self.module = module
        self.locale = locale
        pass

    @property
    def localpath(self) -> str:
        if self.module:
            return mozpath.join(self.locale, self.module, self.file)
        return self.file

    def __hash__(self) -> int:
        return hash(self.localpath)

    def __str__(self):
        return self.fullpath

    def __eq__(self, other: Union[File, str]) -> bool:
        if not isinstance(other, File):
            return False
        return vars(self) == vars(other)

    def __ne__(self, other):
        return not (self == other)
