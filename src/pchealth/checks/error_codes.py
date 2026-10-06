"""裝置管理員錯誤碼（ConfigManagerErrorCode）規則庫。

參考：https://learn.microsoft.com/windows-hardware/drivers/install/device-manager-error-messages
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Severity

REBOOT = "重新開機後再檢查一次。"
REINSTALL = "在裝置管理員對該裝置按右鍵 →「解除安裝裝置」→ 重新開機，讓 Windows 自動重新安裝驅動。"
UPDATE_DRIVER = "到電腦／主機板／該硬體製造商的官方網站下載最新驅動並安裝。"
UPDATE_BIOS = "到主機板製造商官網確認是否有新版 BIOS；更新 BIOS 有風險，請務必依照官方步驟進行，過程中不可斷電。"
RESEAT = "關機拔除電源後，重新插拔該硬體（USB 換一個孔、擴充卡重新插緊）。"


@dataclass(frozen=True)
class ErrorCodeRule:
    severity: Severity
    title: str
    cause: str
    steps: tuple[str, ...]


RULES: dict[int, ErrorCodeRule] = {
    1: ErrorCodeRule(Severity.WARNING, "裝置未正確設定",
                     "裝置沒有安裝驅動，或驅動設定不正確。", (UPDATE_DRIVER, REINSTALL)),
    3: ErrorCodeRule(Severity.WARNING, "驅動程式可能已損毀",
                     "驅動程式損毀，或系統記憶體不足導致無法載入。", (REBOOT, REINSTALL, UPDATE_DRIVER)),
    10: ErrorCodeRule(Severity.CRITICAL, "裝置無法啟動",
                      "驅動程式啟動失敗，常見原因是驅動不相容或硬體故障。", (REINSTALL, UPDATE_DRIVER, RESEAT)),
    12: ErrorCodeRule(Severity.WARNING, "硬體資源衝突",
                      "兩個裝置搶用相同的系統資源（IRQ / 記憶體位址）。",
                      (REBOOT, "移除最近新增的硬體，確認是否與其衝突。", UPDATE_BIOS)),
    14: ErrorCodeRule(Severity.INFO, "需要重新開機",
                      "裝置設定已變更，需要重新開機才會生效。", (REBOOT,)),
    18: ErrorCodeRule(Severity.WARNING, "需要重新安裝驅動",
                      "驅動程式需要重新安裝。", (REINSTALL, UPDATE_DRIVER)),
    19: ErrorCodeRule(Severity.WARNING, "裝置的登錄檔設定損毀",
                      "Windows 登錄檔中此裝置的設定不完整或已損毀。", (REINSTALL,)),
    21: ErrorCodeRule(Severity.INFO, "裝置正在移除中",
                      "Windows 正在移除此裝置。", (REBOOT,)),
    22: ErrorCodeRule(Severity.INFO, "裝置已被停用",
                      "此裝置在裝置管理員中被手動停用了。如果是你自己停用的，可以忽略。",
                      ("若需要使用，在裝置管理員對該裝置按右鍵 →「啟用裝置」。",)),
    24: ErrorCodeRule(Severity.WARNING, "裝置不存在或運作不正常",
                      "硬體可能沒插好、故障，或驅動尚未安裝完成。", (RESEAT, REINSTALL)),
    28: ErrorCodeRule(Severity.WARNING, "沒有安裝驅動程式",
                      "Windows 認得這個硬體，但找不到可用的驅動，所以它目前無法使用。",
                      (UPDATE_DRIVER, "也可以執行 Windows Update 的「進階選項 → 選用更新 → 驅動程式更新」。")),
    29: ErrorCodeRule(Severity.WARNING, "裝置被韌體（BIOS）停用",
                      "此裝置在 BIOS/UEFI 設定中被關閉，或韌體沒有提供它需要的資源。",
                      ("進入 BIOS 設定，確認該功能（例如音效、網路、USB 控制器）為 Enabled。", UPDATE_BIOS)),
    31: ErrorCodeRule(Severity.WARNING, "無法載入驅動程式",
                      "Windows 無法載入此裝置的驅動。", (REINSTALL, UPDATE_DRIVER)),
    32: ErrorCodeRule(Severity.WARNING, "驅動服務被停用",
                      "此裝置的驅動服務啟動類型被設為停用。", (REINSTALL,)),
    33: ErrorCodeRule(Severity.CRITICAL, "無法判斷裝置需要的資源",
                      "這通常代表硬體故障。", (RESEAT, "若問題持續，硬體可能需要送修或更換。")),
    34: ErrorCodeRule(Severity.WARNING, "裝置需要手動設定",
                      "Windows 無法自動設定此裝置的資源。", ("參考硬體說明書設定，或聯絡製造商。",)),
    35: ErrorCodeRule(Severity.WARNING, "BIOS 缺少此裝置的資訊",
                      "主機板韌體沒有提供正確的資源資訊給此裝置。", (UPDATE_BIOS,)),
    37: ErrorCodeRule(Severity.WARNING, "驅動程式初始化失敗",
                      "驅動程式啟動時回報錯誤。", (REINSTALL, UPDATE_DRIVER)),
    38: ErrorCodeRule(Severity.INFO, "舊版驅動仍在記憶體中",
                      "前一個驅動版本還沒卸載。", (REBOOT,)),
    39: ErrorCodeRule(Severity.WARNING, "驅動程式損毀或遺失",
                      "驅動檔案損毀或不見了。", (REINSTALL, UPDATE_DRIVER)),
    40: ErrorCodeRule(Severity.WARNING, "驅動的登錄檔資訊遺失",
                      "登錄檔中此裝置的服務資訊遺失或錯誤。", (REINSTALL,)),
    41: ErrorCodeRule(Severity.WARNING, "驅動已載入但找不到硬體",
                      "常見於非隨插即用的舊硬體，或硬體已被移除。", (RESEAT, REINSTALL)),
    42: ErrorCodeRule(Severity.WARNING, "偵測到重複的裝置",
                      "系統中出現兩個相同的裝置，可能是驅動錯誤。", (REBOOT, REINSTALL)),
    43: ErrorCodeRule(Severity.CRITICAL, "裝置回報問題，已被 Windows 停止",
                      "硬體或驅動回報了故障。USB 裝置常見於接觸不良或供電不足；顯示卡則可能是驅動或硬體問題。",
                      (RESEAT, REINSTALL, UPDATE_DRIVER, "若換了接口、重灌驅動都無效，硬體本身可能故障。")),
    44: ErrorCodeRule(Severity.INFO, "裝置被應用程式關閉",
                      "某個應用程式或服務關閉了此裝置。", (REBOOT,)),
    47: ErrorCodeRule(Severity.INFO, "已準備安全移除",
                      "此裝置已執行「安全移除硬體」。", ("拔除後重新插入即可再次使用。",)),
    48: ErrorCodeRule(Severity.WARNING, "驅動程式因相容性問題被封鎖",
                      "此驅動已知與 Windows 不相容，被系統封鎖。", (UPDATE_DRIVER,)),
    49: ErrorCodeRule(Severity.WARNING, "系統登錄檔過大",
                      "登錄檔超過大小限制，Windows 無法再啟動新裝置。", ("移除不再使用的裝置與軟體後重新開機。",)),
    52: ErrorCodeRule(Severity.WARNING, "驅動程式的數位簽章無法驗證",
                      "驅動沒有有效的數位簽章，可能是非官方或被竄改的驅動。",
                      ("從硬體製造商官網重新下載正式驅動安裝。", REINSTALL)),
}

# 45 = 裝置目前未連接（例如拔掉的 USB 隨身碟），屬正常現象，不列入報告。
IGNORED_CODES = {45}


def rule_for(code: int) -> ErrorCodeRule:
    return RULES.get(code, ErrorCodeRule(
        Severity.WARNING, f"裝置回報錯誤碼 {code}", "這是較少見的錯誤碼。",
        (REINSTALL, UPDATE_DRIVER, f"可搜尋「裝置管理員 錯誤碼 {code}」了解更多。")))
