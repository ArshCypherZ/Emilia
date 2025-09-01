from typing import Iterable
from Emilia import OWNER_ID, DEV_USERS

DEV_SET = set(int(x) for x in (DEV_USERS or []))
DEV_SET.add(int(OWNER_ID))


def is_owner(user_id: int) -> bool:
    try:
        return int(user_id) == int(OWNER_ID)
    except Exception:
        return False


def is_dev(user_id: int) -> bool:
    try:
        return int(user_id) in DEV_SET
    except Exception:
        return False


def any_dev(user_ids: Iterable[int]) -> bool:
    try:
        return any(int(u) in DEV_SET for u in user_ids or [])
    except Exception:
        return False
