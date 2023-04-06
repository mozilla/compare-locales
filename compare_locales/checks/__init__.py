# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Union

from .android import AndroidChecker
from .base import Checker, EntityPos
from .dtd import DTDChecker
from .fluent import FluentChecker
from .properties import PropertiesChecker

if TYPE_CHECKING:
    from ..paths import File


__all__ = [
    "Checker",
    "EntityPos",
    "AndroidChecker",
    "DTDChecker",
    "FluentChecker",
    "PropertiesChecker",
]


def getChecker(
    file: File, extra_tests: Optional[List[str]] = None
) -> Union[DTDChecker, PropertiesChecker, Checker, FluentChecker, AndroidChecker]:
    if PropertiesChecker.use(file):
        return PropertiesChecker(extra_tests, locale=file.locale)
    if DTDChecker.use(file):
        return DTDChecker(extra_tests, locale=file.locale)
    if FluentChecker.use(file):
        return FluentChecker(extra_tests, locale=file.locale)
    if AndroidChecker.use(file):
        return AndroidChecker(extra_tests, locale=file.locale)
    return Checker(extra_tests, locale=file.locale)
