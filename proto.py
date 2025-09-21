from typing import Literal

from pydantic import BaseModel


class NumberPlate(BaseModel):
    number: str
    level: Literal["pin", "ter"]
    zodiac: str | None = None
    five_elem: str | None = None
    color: str | None = None
    size: str | None = None
    sidedness: str | None = None
    sidedness_merge: str | None = None
    sidedness_count: str | None = None
    fauna: str | None = None


class Phase(BaseModel):
    phase: str
    pin: list[str | int]
    ter: str | int
