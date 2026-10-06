"""所有檢查器共用的結果格式。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    OK = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return {0: "正常", 1: "資訊", 2: "注意", 3: "問題"}[self.value]


@dataclass
class Action:
    """附在問題上的捷徑，例如開啟裝置管理員或下載頁。"""
    label: str
    target: str  # 可給 os.startfile 開啟的程式（devmgmt.msc）或網址


@dataclass
class Finding:
    id: str  # 穩定的識別碼，用來跟上一次檢查比對
    severity: Severity
    title: str
    detail: str = ""  # 發生了什麼
    cause: str = ""  # 為什麼會這樣、影響是什麼
    steps: list[str] = field(default_factory=list)  # 建議的解決步驟
    actions: list[Action] = field(default_factory=list)


@dataclass
class CheckResult:
    check_id: str
    title: str
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None  # 檢查本身無法執行時的原因
    raw: object = None  # 原始資料，可匯出成假資料

    @property
    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.OK)

    def to_dict(self) -> dict:
        return asdict(self)
