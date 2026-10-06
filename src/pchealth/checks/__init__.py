from .base import Check
from .devices import DevicesCheck
from .events import EventsCheck
from .gpu import NvidiaCheck
from .performance import PerformanceCheck
from .security import SecurityCheck
from .sensors import SensorsCheck
from .storage import StorageCheck
from .system import SystemCheck

# 順序有意義：SystemCheck 提供的主機板資訊會給後面的檢查器使用
ALL_CHECKS: list[Check] = [SystemCheck(), DevicesCheck(), SensorsCheck(), NvidiaCheck(), StorageCheck(),
                           EventsCheck(), SecurityCheck(), PerformanceCheck()]
