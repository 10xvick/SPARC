from __future__ import annotations
from pydantic import BaseModel
from pathlib import Path

class Foo(BaseModel):
    bar: Path | None = None

print("Pydantic works")
