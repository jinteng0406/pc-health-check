# PC Health Check

家用 Windows 電腦的健康檢查工具。按一下就會檢查整台電腦，用白話說明發現的問題，並告訴你該怎麼處理。

- 程式**只讀取資訊、提供建議**，不會自動修改系統。
- 檢查紀錄只存在本機（`%LOCALAPPDATA%\PCHealthCheck\history`），不會上傳。程式唯一一次連網，是查詢 GitHub 上有沒有新版本。

## 目前的檢查項目（v0.1）

| 項目 | 內容 |
|---|---|
| 裝置與驅動程式 | 裝置管理員中所有回報錯誤的裝置（主機板晶片組、顯示卡、USB／接口、音效、網卡…），附錯誤原因與解決步驟 |

規劃中：硬碟健康（SMART）、NVIDIA 顯示卡狀態、系統狀態（更新、藍屏紀錄、事件日誌）、溫度／風扇感測器。

## 下載與使用

1. 到 [Releases](../../releases/latest) 下載 `PCHealthCheck-vX.Y.Z.zip`。
2. 解壓縮到任一資料夾（例如 `D:\Tools\PCHealthCheck`），**不要**直接在 zip 裡執行。
3. 雙擊 `PCHealthCheck.exe`。

### 第一次執行可能遇到的警告

- **瀏覽器提示「不常下載的檔案」**：選「保留」。
- **藍色視窗「Windows 已保護您的電腦」**：按「其他資訊」→「仍要執行」。程式沒有付費的數位簽章，所以會出現這個提示。
- **UAC「是否允許此應用程式變更您的裝置」**：按「是」才能使用完整功能。按「否」程式仍會執行，但部分檢查會顯示「無法檢查」。

有新版本時，視窗右下角會出現提示和下載連結。

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

假資料模式只是把 `collect()` 換成讀取 `fixtures/<檢查器id>.json`。在家用「匯出原始資料」存下的 JSON，可以直接拿來當新的樣本。

### 發佈新版本

1. 修改 `src/pchealth/__init__.py` 的 `__version__`
2. `git tag v0.2.0 && git push --tags`
3. GitHub Actions 會自動測試、打包，並發佈到 Releases
