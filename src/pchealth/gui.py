"""PySide6 主視窗。"""
from __future__ import annotations

import html
import json
import os

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__, history, runner, updater
from .model import Severity

COLORS = {Severity.OK: "#2e9d5b", Severity.INFO: "#3b82f6",
          Severity.WARNING: "#e0a100", Severity.CRITICAL: "#d64545"}
ERROR_COLOR = "#8a8a8a"

WELCOME = """
<h2>歡迎使用 PC Health Check</h2>
<p>按上方的 <b>「開始檢查」</b>，程式會檢查這台電腦並列出發現的問題。</p>
<p>點左邊任一項目，這裡會顯示：<b>發生了什麼、為什麼、該怎麼處理</b>。</p>
<p style="color:#777">程式只會讀取資訊、提供建議，不會自動修改你的系統。
檢查紀錄只存在這台電腦裡，不會上傳。</p>
"""


def dot_icon(color: str) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, 12, 12)
    p.end()
    return QIcon(pix)


class CheckWorker(QThread):
    done = Signal(dict)

    def __init__(self, demo: bool):
        super().__init__()
        self.demo = demo

    def run(self):
        self.done.emit(runner.run_all(self.demo))


class UpdateWorker(QThread):
    done = Signal(dict)

    def run(self):
        self.done.emit(updater.check())


class MainWindow(QMainWindow):
    def __init__(self, demo: bool, admin: bool):
        super().__init__()
        self.demo, self.admin = demo, admin
        self.report: dict | None = None
        self.setWindowTitle(f"{APP_NAME} v{__version__}" + ("（假資料模式）" if demo else ""))
        self.resize(1050, 780)

        self.run_btn = QPushButton("開始檢查")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.clicked.connect(self.start_check)
        self.export_btn = QPushButton("匯出原始資料")
        self.export_btn.setToolTip("把這次收集到的原始資料存成 JSON，方便開發時建立樣本或拿去問人")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_raw)

        badges = []
        if demo:
            badges.append(("假資料模式", "#7c3aed"))
        badges.append(("管理員權限", COLORS[Severity.OK]) if admin
                      else ("一般權限：部分檢查受限", COLORS[Severity.WARNING]))
        top = QHBoxLayout()
        top.addWidget(self.run_btn)
        top.addWidget(self.export_btn)
        top.addStretch()
        for text, color in badges:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:white;background:{color};border-radius:4px;padding:3px 8px;")
            top.addWidget(lbl)

        self.summary = QLabel("尚未檢查")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["項目", "狀態"])
        self.tree.setColumnWidth(0, 330)
        self.tree.currentItemChanged.connect(self.show_item)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(self.open_link)
        self.detail.setHtml(WELCOME)
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.detail)
        splitter.setSizes([420, 580])

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.summary)
        layout.addWidget(splitter, 1)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.update_label = QLabel()
        self.update_label.setOpenExternalLinks(True)
        self.statusBar().addWidget(QLabel(f"版本 {__version__}"))
        self.statusBar().addPermanentWidget(self.update_label)
        self.update_worker = UpdateWorker()
        self.update_worker.done.connect(self.on_update_checked)
        self.update_worker.start()

    # ---- 檢查流程 ----
    def start_check(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("檢查中…")
        self.summary.setText("正在檢查，請稍候…")
        self.worker = CheckWorker(self.demo)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def on_done(self, report: dict):
        self.report = report
        self.run_btn.setEnabled(True)
        self.run_btn.setText("重新檢查")
        self.export_btn.setEnabled(True)

        folder = history.history_dir(self.demo)
        change = history.diff(history.load_latest(folder), report)
        try:
            history.save(report, folder)
        except OSError:
            pass
        self.populate(report)
        self.summary.setText(self.summary_html(report, change))

    def populate(self, report: dict):
        self.tree.clear()
        first_problem = None
        for res in report["results"]:
            if res["error"]:
                top = QTreeWidgetItem([res["title"], "無法檢查"])
                top.setIcon(0, dot_icon(ERROR_COLOR))
            else:
                worst = Severity(max((f["severity"] for f in res["findings"]), default=0))
                top = QTreeWidgetItem([res["title"], worst.label])
                top.setIcon(0, dot_icon(COLORS[worst]))
            top.setData(0, Qt.UserRole, ("check", res))
            self.tree.addTopLevelItem(top)
            for f in res["findings"]:
                sev = Severity(f["severity"])
                child = QTreeWidgetItem([f["title"], sev.label])
                child.setIcon(0, dot_icon(COLORS[sev]))
                child.setData(0, Qt.UserRole, ("finding", f))
                top.addChild(child)
                if first_problem is None and sev >= Severity.WARNING:
                    first_problem = child
            top.setExpanded(True)
        self.tree.setCurrentItem(first_problem or self.tree.topLevelItem(0))

    def summary_html(self, report: dict, change: history.Diff | None) -> str:
        counts = {s: 0 for s in Severity}
        errors = 0
        for res in report["results"]:
            errors += bool(res["error"])
            for f in res["findings"]:
                counts[Severity(f["severity"])] += 1
        parts = [f"<b>檢查完成</b>（{report['timestamp'].replace('T', ' ')}）："]
        if counts[Severity.CRITICAL] or counts[Severity.WARNING]:
            parts.append(f"<span style='color:{COLORS[Severity.CRITICAL]}'>問題 {counts[Severity.CRITICAL]} 項</span>、"
                         f"<span style='color:{COLORS[Severity.WARNING]}'>注意 {counts[Severity.WARNING]} 項</span>")
        else:
            parts.append(f"<span style='color:{COLORS[Severity.OK]}'>沒有發現需要處理的問題</span>")
        if errors:
            parts.append(f"，{errors} 個項目無法檢查")
        if change:
            parts.append(f"<br>與上次（{change.previous_time.replace('T', ' ')}）相比：")
            if not change.new and not change.resolved:
                parts.append("沒有變化")
            if change.new:
                parts.append(f"<span style='color:{COLORS[Severity.CRITICAL]}'>新增 {len(change.new)} 個問題</span> ")
            if change.resolved:
                parts.append(f"<span style='color:{COLORS[Severity.OK]}'>已解決 {len(change.resolved)} 個問題</span>")
        return "".join(parts)

    # ---- 詳細資訊 ----
    def show_item(self, item: QTreeWidgetItem | None, _prev=None):
        if item is None:
            return
        kind, data = item.data(0, Qt.UserRole)
        self.detail.setHtml(self.check_html(data) if kind == "check" else self.finding_html(data))

    @staticmethod
    def check_html(res: dict) -> str:
        e = html.escape
        if res["error"]:
            return (f"<h2>{e(res['title'])}</h2><p style='color:{ERROR_COLOR}'><b>這個項目無法檢查</b></p>"
                    f"<p>{e(res['error'])}</p><p>如果是權限問題，請以系統管理員身分重新執行程式。</p>")
        rows = "".join(f"<li>{e(f['title'])}</li>" for f in res["findings"])
        return f"<h2>{e(res['title'])}</h2><ul>{rows}</ul><p style='color:#777'>點選個別項目查看詳細說明。</p>"

    @staticmethod
    def finding_html(f: dict) -> str:
        e = html.escape
        sev = Severity(f["severity"])
        out = [f"<h2>{e(f['title'])}</h2>",
               f"<p><span style='color:white;background:{COLORS[sev]};padding:2px 8px'>&nbsp;{sev.label}&nbsp;</span></p>"]
        if f["detail"]:
            out.append("<h3>發生了什麼</h3><p>" + e(f["detail"]).replace("\n", "<br>") + "</p>")
        if f["cause"]:
            out.append(f"<h3>原因與影響</h3><p>{e(f['cause'])}</p>")
        if f["steps"]:
            out.append("<h3>建議的解決步驟</h3><ol>" +
                       "".join(f"<li style='margin-bottom:4px'>{e(s)}</li>" for s in f["steps"]) + "</ol>")
        if f["actions"]:
            links = " ｜ ".join(f"<a href='{e(_href(a['target']))}'>{e(a['label'])}</a>" for a in f["actions"])
            out.append(f"<h3>捷徑</h3><p>{links}</p>")
        return "".join(out)

    def open_link(self, url: QUrl):
        if url.scheme() == "run":
            target, _, args = url.path().partition(" ")  # 例如 "perfmon.exe /rel"
            try:
                os.startfile(target, arguments=args) if args else os.startfile(target)
            except OSError as e:
                QMessageBox.warning(self, APP_NAME, f"無法開啟：{e}")
        else:
            QDesktopServices.openUrl(url)

    # ---- 其他 ----
    def export_raw(self):
        if not self.report:
            return
        name = f"pchealth-raw-{self.report['timestamp'].replace(':', '-')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "匯出原始資料", name, "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(self.report, fp, ensure_ascii=False, indent=2)

    def on_update_checked(self, result: dict):
        kind = result.get("kind")
        self.update_label.setToolTip("已找到 OneDrive 的 PCHealthCheck 資料夾" if result.get("onedrive_found")
                                     else "找不到 OneDrive 的 PCHealthCheck 資料夾，新版提示會改連到 GitHub")
        if kind in ("onedrive", "github"):
            url = (QUrl.fromLocalFile(result["target"]).toString() if kind == "onedrive" else result["target"])
            text = "已在 OneDrive，點此開啟資料夾" if kind == "onedrive" else "點此下載"
            self.update_label.setText(
                f"<a href='{html.escape(url)}' style='color:{COLORS[Severity.CRITICAL]}'>"
                f"有新版本 {html.escape(result['tag'])}，{text}</a>")
        elif kind == "latest":
            self.update_label.setText(f"<span style='color:{COLORS[Severity.OK]}'>已是最新版本</span>")
        else:
            self.update_label.setText(f"<span style='color:{ERROR_COLOR}'>無法檢查新版本（可能沒有網路）</span>")


def _href(target: str) -> str:
    return target if target.startswith(("http://", "https://")) else f"run:{target}"


def run_app(demo: bool, admin: bool) -> int:
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Microsoft JhengHei UI", 10))
    win = MainWindow(demo, admin)
    win.show()
    return app.exec()
