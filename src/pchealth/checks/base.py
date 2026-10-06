from __future__ import annotations

from ..model import CheckResult, Finding


class Check:
    """一個檢查器 = 收集原始資料（collect）+ 用規則判斷（analyze）。

    兩者分開，假資料模式只要換掉 collect 的結果就能測試 analyze。
    ctx 是前面的檢查器透過 context() 提供的共用資訊（例如主機板型號）。
    """
    id: str = ""
    title: str = ""

    def collect(self) -> object:
        raise NotImplementedError

    def analyze(self, raw: object, ctx: dict) -> list[Finding]:
        raise NotImplementedError

    def context(self, raw: object) -> dict:
        """提供給後續檢查器的資訊，預設沒有。"""
        return {}

    def run(self, raw: object | None = None, ctx: dict | None = None) -> CheckResult:
        try:
            if raw is None:
                raw = self.collect()
            return CheckResult(self.id, self.title, self.analyze(raw, ctx or {}), raw=raw)
        except Exception as e:  # 單一檢查失敗不影響其他檢查
            return CheckResult(self.id, self.title, error=f"{type(e).__name__}: {e}", raw=raw)
