from enum import IntEnum, unique
from typing import Union


@unique
class Faction(IntEnum):
    arm = 0
    core = 1
    gok = 2

    @staticmethod
    def from_string(value: str) -> "Faction":
        return Faction.__members__[value.lower()]

    @staticmethod
    def from_value(value: Union[str, int]) -> "Faction":
        if isinstance(value, str):
            return Faction.from_string(value)
        elif isinstance(value, int):
            return Faction(value)

        raise TypeError(f"Unsupported faction type {type(value)}!")
