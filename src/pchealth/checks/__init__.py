from .base import Check
from .devices import DevicesCheck
from .storage import StorageCheck
from .system import SystemCheck

# 順序有意義：SystemCheck 提供的主機板資訊會給後面的檢查器使用
ALL_CHECKS: list[Check] = [SystemCheck(), DevicesCheck(), StorageCheck()]
