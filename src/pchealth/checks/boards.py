"""主機板品牌：把 WMI 的製造商全名轉成常見品牌名，並提供官方支援頁。"""
from __future__ import annotations

from ..model import Action

BRANDS = [  # (WMI 製造商名稱中的關鍵字, 品牌, 支援頁)
    ("ASUS", "ASUS", "https://www.asus.com/support/"),
    ("MICRO-STAR", "MSI", "https://www.msi.com/support"),
    ("MSI", "MSI", "https://www.msi.com/support"),
    ("GIGABYTE", "GIGABYTE", "https://www.gigabyte.com/Support"),
    ("ASROCK", "ASRock", "https://www.asrock.com/support/index.asp"),
]


def brand_of(manufacturer: str | None) -> tuple[str, str | None]:
    """回傳 (品牌名, 支援頁)；不認得時回傳原名與 None。"""
    name = (manufacturer or "").strip()
    upper = name.upper()
    for key, brand, url in BRANDS:
        if key in upper:
            return brand, url
    return name, None


def board_support(ctx: dict) -> tuple[str, Action | None] | None:
    """若已知主機板型號，回傳 (建議步驟, 支援頁捷徑)。"""
    board = ctx.get("board")
    if not board:
        return None
    url = ctx.get("board_support_url")
    step = (f"你的主機板是 {board}：到 {ctx.get('board_brand') or '製造商'} 官網搜尋這個型號，"
            "在「驅動程式與工具」下載對應的晶片組（Chipset）、音效、網路驅動。")
    return step, (Action(f"{ctx.get('board_brand')} 支援頁", url) if url else None)
