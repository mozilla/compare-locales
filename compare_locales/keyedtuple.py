# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""A tuple with keys.

A Sequence type that allows to refer to its elements by key.
Making this immutable, 'cause keeping track of mutations is hard.

compare-locales uses strings for Entity keys, and tuples in the
case of PO. Support both.

In the interfaces that check for membership, dicts check keys and
sequences check values. Always try our dict cache `__map` first,
and fall back to the superclass implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Iterator, Tuple, Type, Union, cast

if TYPE_CHECKING:
    from .parser import Entity, Junk


class KeyedTuple(Tuple[Union[Entity, Junk], ...]):
    def __new__(
        cls: Type[KeyedTuple], iterable: Iterable[Union[Entity, Junk]]
    ) -> KeyedTuple:
        return super().__new__(cls, iterable)  # type: ignore

    def __init__(self, iterable: Iterable[Union[Entity, Junk]]) -> None:
        self.__map = {}
        if iterable:
            for index, item in enumerate(self):
                self.__map[item.key] = index

    def __contains__(self, key: object) -> bool:
        try:
            contains = key in self.__map
            if contains:
                return True
        except TypeError:
            pass
        return super().__contains__(key)

    def __getitem__(self, key: Union[str, int]) -> Union[Entity, Junk]:  # type:ignore
        try:
            key = self.__map[key]
        except (KeyError, TypeError):
            pass
        return super().__getitem__(cast(int, key))

    def keys(self) -> Iterator[str]:
        for value in self:
            yield value.key

    def items(self) -> Iterator[Tuple[str, Union[Entity, Junk]]]:
        for value in self:
            yield value.key, value

    def values(self) -> "KeyedTuple":
        return self
