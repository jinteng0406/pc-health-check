# PC Health Check

家用 Windows 電腦的健康檢查工具。按一下就會檢查整台電腦，用白話說明發現的問題，並告訴你該怎麼處理。

- 程式**只讀取資訊、提供建議**，不會自動修改系統。
- 檢查紀錄只存在本機（`%LOCALAPPDATA%\PCHealthCheck\history`），不會上傳。程式唯一一次連網，是查詢 GitHub 上有沒有新版本。

## 目前的檢查項目（v0.3）

| 項目 | 內容 |
|---|---|
| 這台電腦 | 主機板、BIOS、CPU、記憶體、顯示卡與驅動版本、Windows 版本；提醒顯示卡驅動過舊、太久沒重新啟動、BIOS 過舊 |
| 裝置與驅動程式 | 裝置管理員中所有回報錯誤的裝置（主機板晶片組、顯示卡、USB／接口、音效、網卡…），附錯誤原因與解決步驟；會依你的主機板型號指向正確的支援頁 |
| 顯示卡狀態 | NVIDIA 顯示卡的溫度、風扇、功耗、使用率；**PCIe 插槽連線寬度**（偵測顯示卡沒插好）；過熱降頻、供電不足降速 |
| 硬碟健康與容量 | SMART 自我檢測、無法修復的讀寫錯誤、NVMe 嚴重警告與備用區、壞軌（HDD／SATA SSD）、磨損程度、溫度、通電時數（需管理員權限，使用內附的 smartctl）；各磁碟區剩餘空間與檔案系統錯誤 |

規劃中：系統狀態（Windows 更新、藍屏紀錄、事件日誌、Defender）、CPU／主機板溫度與風扇感測器。

有新版本時，如果 OneDrive 的 `PCHealthCheck` 資料夾裡已經有新版 zip，右下角的提示會直接開啟那個資料夾；否則連到 GitHub 下載頁。

## 下載與使用

1. 到 [Releases](../../releases/latest) 下載 `PCHealthCheck-vX.Y.Z.zip`。
2. 解壓縮到任一資料夾（例如 `D:\Tools\PCHealthCheck`），**不要**直接在 zip 裡執行。
3. 雙擊 `PCHealthCheck.exe`。

### 第一次執行可能遇到的警告

- **瀏覽器提示「不常下載的檔案」**：選「保留」。
- **藍色視窗「Windows 已保護您的電腦」**：按「其他資訊」→「仍要執行」。程式沒有付費的數位簽章，所以會出現這個提示。
- **UAC「是否允許此應用程式變更您的裝置」**：按「是」才能使用完整功能。按「否」程式仍會執行，但部分檢查會顯示「無法檢查」。

## 開發

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python run.py --demo        # 假資料模式：使用 fixtures/ 中的故障情境，不需要管理員權限
python run.py               # 讀取真實硬體
python -m pytest            # 測試
.\build.ps1                 # 打包成 dist\PCHealthCheck\
```

### 架構

每個檢查器（`src/pchealth/checks/`）分成兩步：

- `collect()`：讀取原始資料（PowerShell / WMI 等）
- `analyze(raw)`：依規則庫產生 `Finding`（嚴重度、發生了什麼、原因、解決步驟、捷徑）

檢查器依序執行，前面的檢查器可以透過 `context()` 提供資訊給後面的（例如「這台電腦」提供主機板型號，讓裝置檢查能指向正確的支援頁）。

假資料模式只是把 `collect()` 換成讀取 `fixtures/<檢查器id>.json`。

### 把真實資料變成測試樣本

在目標電腦按「匯出原始資料」，帶回來後執行：

```powershell
python tools\sanitize_export.py pchealth-raw-XXXX.json tests\data\<名稱>
```

會遮掉序號、MAC 位址、GUID 等可識別資訊，才能放進公開 repo。

### 發佈新版本

1. 修改 `src/pchealth/__init__.py` 的 `__version__`
2. `git tag v0.2.0 && git push --tags`
3. GitHub Actions 會自動測試、打包，並發佈到 Releases
