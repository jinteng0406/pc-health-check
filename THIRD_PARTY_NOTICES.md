# 第三方軟體聲明

## smartmontools（smartctl.exe）

打包版的 `_internal/bin/smartctl.exe` 來自 smartmontools，用於讀取硬碟的 SMART 健康資料。

- 授權：GNU General Public License v2（全文見 `_internal/bin/COPYING.txt`）
- 原始碼與官方網站：https://www.smartmontools.org/ 、 https://github.com/smartmontools/smartmontools
- PC Health Check 只以獨立程式的方式呼叫 smartctl，沒有修改它。

## LibreHardwareMonitor（_internal/bin/lhm）

讀取 CPU 溫度、主機板溫度、風扇與電壓用的函式庫，**只有在電腦已安裝 PawnIO 驅動時才會載入**。
本程式不會安裝 PawnIO 或任何驅動程式。

- LibreHardwareMonitorLib 0.9.6：Mozilla Public License 2.0
  原始碼：https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/tree/v0.9.6
- 隨附的相依函式庫：HidSharp（Apache License 2.0）、Microsoft .NET 相關組件 System.*、Microsoft.Bcl.*（MIT），
  以及 LibreHardwareMonitor 專案使用的 BlackSharp.Core、DiskInfoToolkit、RAMSPDToolkit-NDD（授權見各自專案）
- 皆未經修改，直接取自 LibreHardwareMonitor v0.9.6 官方發佈檔

## Qt / PySide6

介面使用 PySide6（Qt for Python），授權為 LGPLv3。
- https://www.qt.io/qt-for-python
