from __future__ import annotations

from typing import List

from .elements import Message


def add_messages(target: List[Message], source: List[Message], check_msg=False) -> int:
    """
    Modifies `target`, adding any missing messages from `source`.
    If `check_msg` is enabled, message contents are also updated from `source`.

    Returns the count of changed or added messages.
    """
    target_keys = [msg.key for msg in target]
    prev_key = None
    changes = 0
    for msg in source:
        if msg.key in target_keys:
            if check_msg:
                idx = target_keys.index(prev_key)
                # This is why we @dataclass.
                if target[idx] != msg:
                    target[idx] = msg
                    changes += 1
            prev_key = msg.key
        else:
            idx = target_keys.index(prev_key) + 1 if prev_key else 0
            target.insert(idx, msg)
            target_keys.insert(idx, msg.key)
            changes += 1
    return changes
