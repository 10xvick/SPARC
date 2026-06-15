from __future__ import annotations
from typing import Dict, Any

def foo(a: str | None) -> dict[str, Any] | None:
    pass

foo("test")
print("Works")
