from .base import Check
from .devices import DevicesCheck

ALL_CHECKS: list[Check] = [DevicesCheck()]
