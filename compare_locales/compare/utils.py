# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"Mozilla l10n compare locales tool"
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, List, Tuple, Type, Union

from .. import paths

if TYPE_CHECKING:
    from ..parser import Whitespace
    from ..parser.android import XMLWhitespace


class Tree:
    def __init__(self, valuetype: Union[Type[list], Type[dict]]) -> None:
        self.branches = dict()
        self.valuetype = valuetype
        self.value = None

    def __getitem__(self, leaf: Union[str, paths.File]) -> List[Dict[str, str]]:
        parts = []
        if isinstance(leaf, paths.File):
            parts = []
            if leaf.module:
                parts += [leaf.locale] + leaf.module.split("/")
            parts += leaf.file.split("/")
        else:
            parts = leaf.split("/")
        return self.__get(parts)

    def __get(self, parts):
        common = None
        old = None
        new = tuple(parts)
        t = self
        for k, v in self.branches.items():
            for i, part in enumerate(zip(k, parts)):
                if part[0] != part[1]:
                    i -= 1
                    break
            if i < 0:
                continue
            i += 1
            common = tuple(k[:i])
            old = tuple(k[i:])
            new = tuple(parts[i:])
            break
        if old:
            self.branches.pop(k)
            t = Tree(self.valuetype)
            t.branches[old] = v
            self.branches[common] = t
        elif common:
            t = self.branches[common]
        if new:
            if common:
                return t.__get(new)
            t2 = t
            t = Tree(self.valuetype)
            t2.branches[new] = t
        if t.value is None:
            t.value = t.valuetype()
        return t.value

    indent = "  "

    def getContent(
        self, depth: int = 0
    ) -> Iterator[
        Union[
            Tuple[int, str, Tuple[str]],
            Tuple[int, str, Dict[str, int]],
            Tuple[int, str, Tuple[str, str]],
        ]
    ]:
        """
        Returns iterator of (depth, flag, key_or_value) tuples.
        If flag is 'value', key_or_value is a value object, otherwise
        (flag is 'key') it's a key string.
        """
        keys = sorted(self.branches.keys())
        if self.value is not None:
            yield (depth, "value", self.value)
        for key in keys:
            yield (depth, "key", key)
            yield from self.branches[key].getContent(depth + 1)

    def toJSON(
        self,
    ) -> Union[
        Dict[str, int],
        Dict[str, Dict[str, Dict[str, int]]],
        List[Dict[str, str]],
        Dict[str, List[Dict[str, str]]],
        Dict[str, Dict[str, int]],
    ]:
        """
        Returns this Tree as a JSON-able tree of hashes.
        Only the values need to take care that they're JSON-able.
        """
        if self.value is not None:
            return self.value
        return {
            "/".join(key): self.branches[key].toJSON() for key in self.branches.keys()
        }

    def getStrRows(self) -> List[str]:
        def tostr(t):
            if t[1] == "key":
                return self.indent * t[0] + "/".join(t[2])
            return self.indent * (t[0] + 1) + str(t[2])

        return [tostr(c) for c in self.getContent()]

    def __str__(self) -> str:
        return "\n".join(self.getStrRows())


class AddRemove:
    def __init__(self) -> None:
        self.left = self.right = None

    def set_left(self, left: List[str]) -> None:
        if not isinstance(left, list):
            left = list(li for li in left)
        self.left = left

    def set_right(self, right: List[str]) -> None:
        if not isinstance(right, list):
            right = list(li for li in right)
        self.right = right

    def __iter__(
        self,
    ) -> Iterator[
        Union[
            Tuple[str, str],
            Tuple[str, XMLWhitespace],
            Tuple[str, Tuple[str, int]],
            Tuple[str, Whitespace],
        ]
    ]:
        # order_map stores index in left and then index in right
        order_map = {item: (i, -1) for i, item in enumerate(self.left)}
        left_items = set(order_map)
        # as we go through the right side, keep track of which left
        # item we had in right last, and for items not in left,
        # set the sortmap to (left_offset, right_index)
        left_offset = -1
        right_items = set()
        for i, item in enumerate(self.right):
            right_items.add(item)
            if item in order_map:
                left_offset = order_map[item][0]
            else:
                order_map[item] = (left_offset, i)
        for item in sorted(order_map, key=lambda item: order_map[item]):
            if item in left_items and item in right_items:
                yield ("equal", item)
            elif item in left_items:
                yield ("delete", item)
            else:
                yield ("add", item)
