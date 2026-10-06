"""常見藍屏（BugCheck）錯誤碼的白話說明。

參考：https://learn.microsoft.com/windows-hardware/drivers/debugger/bug-check-code-reference2
"""
from __future__ import annotations

# 代碼 → (名稱, 常見原因, 建議第一步)
BUGCHECKS: dict[int, tuple[str, str, str]] = {
    0x0A: ("IRQL_NOT_LESS_OR_EQUAL", "某個驅動程式存取了不該存取的記憶體，通常是驅動程式有問題。",
           "更新最近安裝或更新過的驅動程式（顯示卡、網路、音效）。"),
    0x1A: ("MEMORY_MANAGEMENT", "記憶體管理發生錯誤，常見原因是記憶體條不穩定或故障。",
           "到 BIOS 暫時關閉 XMP（記憶體超頻），並用「Windows 記憶體診斷」檢查記憶體。"),
    0x3B: ("SYSTEM_SERVICE_EXCEPTION", "系統服務執行時出錯，常見於驅動程式或防毒軟體衝突。",
           "更新顯示卡驅動；若最近裝了新的防毒或系統工具，先移除試試。"),
    0x50: ("PAGE_FAULT_IN_NONPAGED_AREA", "讀取了不存在的記憶體位址，可能是驅動程式或記憶體有問題。",
           "更新驅動程式，並用「Windows 記憶體診斷」檢查記憶體。"),
    0x7E: ("SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", "系統執行緒出現未處理的錯誤，通常是驅動程式造成。",
           "更新或回復最近變更過的驅動程式。"),
    0x7F: ("UNEXPECTED_KERNEL_MODE_TRAP", "CPU 遇到無法處理的狀況，常見於硬體不穩定或超頻。",
           "取消 CPU／記憶體超頻，確認散熱正常。"),
    0x9F: ("DRIVER_POWER_STATE_FAILURE", "某個驅動程式在睡眠／喚醒時沒有正確回應。",
           "更新晶片組與顯示卡驅動；若常在睡眠後發生，可暫時停用睡眠或快速啟動。"),
    0xC2: ("BAD_POOL_CALLER", "某個驅動程式錯誤地使用了系統記憶體。", "更新驅動程式。"),
    0xD1: ("DRIVER_IRQL_NOT_LESS_OR_EQUAL", "驅動程式存取了無效的記憶體位址，最常見是網路卡或顯示卡驅動。",
           "更新網路卡（有線／無線）與顯示卡驅動。"),
    0xEF: ("CRITICAL_PROCESS_DIED", "Windows 的關鍵程序意外結束，可能是系統檔損毀或硬碟問題。",
           "以系統管理員身分執行「sfc /scannow」修復系統檔，並確認硬碟健康。"),
    0x116: ("VIDEO_TDR_FAILURE", "顯示卡驅動停止回應且無法恢復。",
            "用全新安裝方式重灌顯示卡驅動；取消顯示卡超頻；確認顯示卡供電線插緊。"),
    0x117: ("VIDEO_TDR_TIMEOUT_DETECTED", "顯示卡驅動停止回應。", "重灌顯示卡驅動，並確認顯示卡溫度與供電。"),
    0x124: ("WHEA_UNCORRECTABLE_ERROR", "硬體回報了無法修正的錯誤，常見於 CPU 或記憶體超頻、電壓不足、硬體故障。",
            "取消所有超頻（含 XMP），更新 BIOS；若持續發生，可能是 CPU、記憶體或主機板故障。"),
    0x133: ("DPC_WATCHDOG_VIOLATION", "某個驅動程式卡住太久，常見於儲存裝置（SSD）韌體或驅動。",
            "更新 SSD 韌體、晶片組驅動與 Intel RST 驅動。"),
    0x139: ("KERNEL_SECURITY_CHECK_FAILURE", "系統偵測到資料結構損毀，常見於驅動程式或記憶體問題。",
            "更新驅動程式，並檢查記憶體。"),
    0x154: ("UNEXPECTED_STORE_EXCEPTION", "記憶體壓縮／分頁儲存發生錯誤，常見於硬碟或記憶體問題。",
            "檢查硬碟健康與記憶體。"),
    0x1E: ("KMODE_EXCEPTION_NOT_HANDLED", "核心模式程式發生錯誤，通常是驅動程式。", "更新驅動程式。"),
}


def describe(code: int) -> tuple[str, str, str]:
    return BUGCHECKS.get(code, (f"0x{code:X}", "這是較少見的藍屏代碼。",
                                f"可以搜尋「藍屏 0x{code:X}」了解更多，或更新所有驅動程式。"))


def parse_code(value: str | None) -> int | None:
    """Kernel-Power 41 給十進位（"278"），WER 1001 給 "0x00000116 (0x…, …)"。"""
    if not value:
        return None
    text = value.strip().split(" ")[0]
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None
