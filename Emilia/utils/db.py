__all__ = ["get_collection"]

from motor.core import AgnosticClient, AgnosticCollection, AgnosticDatabase
from typing import Dict, Any, Optional
from Emilia import db as _DATABASE
from Emilia.utils.constants import COLL, normalize_filter


COLLECTIONS = COLL

def get_collection(name: str) -> AgnosticCollection:
    """Create or Get Collection from your database"""
    return _DATABASE[name]

def coll(name: str) -> AgnosticCollection:
    return get_collection(name)

def find_one(name: str, flt: Dict[str, Any], projection: Optional[Dict[str, int]] = None):
    flt = normalize_filter(flt)
    return _DATABASE[name].find_one(flt, projection)

def find(name: str, flt: Dict[str, Any], projection: Optional[Dict[str, int]] = None, *, batch_size: int = 200, limit: Optional[int] = None):
    flt = normalize_filter(flt)
    cursor = _DATABASE[name].find(flt, projection, batch_size=batch_size)
    if limit:
        cursor = cursor.limit(int(limit))
    return cursor
