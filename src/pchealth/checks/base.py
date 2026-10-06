from __future__ import annotations

from ..model import CheckResult, Finding


class Check:
    """一個檢查器 = 收集原始資料（collect）+ 用規則判斷（analyze）。

    兩者分開，假資料模式只要換掉 collect 的結果就能測試 analyze。
    """
    id: str = ""
    title: str = ""

    def collect(self) -> object:
        raise NotImplementedError

    def analyze(self, raw: object) -> list[Finding]:
        raise NotImplementedError

    def run(self, raw: object | None = None) -> CheckResult:
        try:
            if raw is None:
                raw = self.collect()
            return CheckResult(self.id, self.title, self.analyze(raw), raw=raw)
        except Exception as e:  # 單一檢查失敗不影響其他檢查
            return CheckResult(self.id, self.title, error=f"{type(e).__name__}: {e}", raw=raw)
