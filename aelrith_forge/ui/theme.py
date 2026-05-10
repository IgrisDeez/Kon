from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


class Colors:
    window = "#050505"
    surface = "#090909"
    panel = "#101010"
    panel_high = "#171717"
    panel_soft = "#0c0c0c"
    border = "#3d3d3d"
    border_soft = "#242424"
    text = "#f2f2f2"
    muted = "#b8b8b8"
    faint = "#7f7f7f"
    accent = "#d7d7d7"
    accent_2 = "#9a9a9a"
    specs = "#dcdcdc"
    powers = "#bfbfbf"
    good = "#ffffff"
    warn = "#cfcfcf"
    error = "#e7e7e7"


def apply_theme(app: QApplication):
    app.setStyle(QStyleFactory.create("Fusion"))
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(Colors.window))
    palette.setColor(QPalette.WindowText, QColor(Colors.text))
    palette.setColor(QPalette.Base, QColor(Colors.surface))
    palette.setColor(QPalette.AlternateBase, QColor(Colors.panel))
    palette.setColor(QPalette.ToolTipBase, QColor(Colors.panel_high))
    palette.setColor(QPalette.ToolTipText, QColor(Colors.text))
    palette.setColor(QPalette.Text, QColor(Colors.text))
    palette.setColor(QPalette.Button, QColor(Colors.panel_high))
    palette.setColor(QPalette.ButtonText, QColor(Colors.text))
    palette.setColor(QPalette.Highlight, QColor(Colors.accent))
    palette.setColor(QPalette.HighlightedText, QColor("#050505"))
    app.setPalette(palette)

    app.setStyleSheet(
        f"""
        QWidget {{
            background: {Colors.window};
            color: {Colors.text};
            font-size: 9pt;
            selection-background-color: {Colors.accent};
        }}

        QLabel {{
            background: transparent;
            border: 0;
        }}

        QWidget[container="true"] {{
            background: transparent;
            border: 0;
        }}

        QScrollArea {{
            border: 0;
            background: transparent;
        }}

        QMainWindow, #Root {{
            background: {Colors.window};
        }}

        #Sidebar {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #080808, stop:1 #050505);
            border-right: 1px solid {Colors.border_soft};
        }}

        QFrame#SidebarLogoShell {{
            background: transparent;
            border: 0;
        }}

        QLabel[role="logo"] {{
            padding: 1px 0 3px 0;
        }}

        #TopChrome {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #151515, stop:0.58 #101010, stop:1 #121212);
            border: 1px solid {Colors.border};
            border-radius: 13px;
        }}

        QLabel[role="title"] {{
            font-size: 12pt;
            font-weight: 700;
            color: #ffffff;
        }}

        QLabel[role="heroTitle"] {{
            font-size: 14.5pt;
            font-weight: 760;
            color: #ffffff;
            letter-spacing: 0.35px;
        }}

        QLabel[role="subtitle"] {{
            color: #d0d0d0;
            font-size: 8.5pt;
            font-weight: 600;
            letter-spacing: 0.15px;
        }}

        QLabel[role="version"] {{
            font-size: 8pt;
            color: {Colors.faint};
            padding-top: 2px;
        }}

        QLabel[role="section"] {{
            font-size: 10pt;
            font-weight: 650;
            color: #f5f5f5;
        }}

        QLabel[role="muted"] {{
            color: {Colors.muted};
        }}

        QLabel[role="tiny"] {{
            color: {Colors.faint};
            font-size: 8pt;
        }}

        QLabel[role="statusLabel"] {{
            color: {Colors.faint};
            font-size: 8pt;
            font-weight: 600;
        }}

        QLabel[role="statusValue"] {{
            font-weight: 650;
            color: #ffffff;
            background: transparent;
        }}

        QLabel[role="statusMetricValue"] {{
            font-size: 9pt;
            font-weight: 680;
            color: #ffffff;
        }}

        QLabel[role="panelEyebrow"] {{
            color: #c8c8c8;
            font-size: 8pt;
            font-weight: 650;
            letter-spacing: 0.2px;
        }}

        QLabel[role="metricBlockLabel"] {{
            color: #b0b0b0;
            font-size: 7.95pt;
            font-weight: 650;
            letter-spacing: 0.18px;
        }}

        QLabel[role="metricBlockValue"] {{
            color: #f5f5f5;
            font-size: 9pt;
            font-weight: 670;
        }}

        QLabel[role="metricBlockValue"][stateTone="good"] {{
            color: #ffffff;
        }}

        QLabel[role="metricBlockValue"][stateTone="warn"] {{
            color: #d6d6d6;
        }}

        QLabel[role="metricBlockValue"][stateTone="error"] {{
            color: #eeeeee;
        }}

        QLabel[summary="true"] {{
            background: #0d0d0d;
            border: 1px solid {Colors.border_soft};
            border-radius: 8px;
            padding: 6px 8px;
            color: #d8d8d8;
        }}

        QLabel[summaryContent="true"] {{
            color: #ffffff;
        }}

        QLabel[badge="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222222, stop:1 #151515);
            border: 1px solid #565656;
            border-radius: 8px;
            padding: 3px 8px;
            color: #f8f8f8;
            font-weight: 650;
        }}

        QLabel[badge="true"][pill="true"] {{
            background: #141414;
            border-color: #333333;
            color: #d0d0d0;
            font-size: 8pt;
            font-weight: 620;
        }}

        QLabel[badge="true"][statusTone="header"] {{
            padding: 4px 10px;
            border-radius: 8px;
        }}

        QLabel[badge="true"][stateTone="idle"] {{
            background: #151515;
            border-color: #444444;
            color: #e5e5e5;
        }}

        QLabel[badge="true"][stateTone="good"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #303030, stop:1 #202020);
            border-color: #777777;
            color: #ffffff;
        }}

        QLabel[badge="true"][stateTone="warn"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #242424, stop:1 #181818);
            border-color: #666666;
            color: #e0e0e0;
        }}

        QLabel[badge="true"][stateTone="error"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2a2a, stop:1 #161616);
            border-color: #a0a0a0;
            color: #ffffff;
        }}

        QLabel[previewNotice="true"] {{
            background: #151515;
            border: 1px solid #686868;
            border-radius: 8px;
            color: #ffffff;
            padding: 4px 10px;
            font-size: 8pt;
            font-weight: 650;
        }}

        QLabel[modeBadge="true"] {{
            min-width: 56px;
            padding: 3px 9px;
        }}

        QLabel[modeBadge="true"][modeActive="false"] {{
            background: #0d0d0d;
            border-color: #2a2a2a;
            color: #858585;
        }}

        QLabel[modeBadge="true"][modeTone="idle"][modeActive="true"] {{
            background: #151515;
            border-color: #444444;
            color: #e5e5e5;
        }}

        QLabel[modeBadge="true"][modeTone="specs"][modeActive="true"] {{
            background: #1b1b1b;
            border-color: {Colors.specs};
            color: #ffffff;
        }}

        QLabel[modeBadge="true"][modeTone="powers"][modeActive="true"] {{
            background: #171717;
            border-color: {Colors.powers};
            color: #eeeeee;
        }}

        QFrame[card="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121212, stop:1 #0c0c0c);
            border: 1px solid {Colors.border};
            border-radius: 8px;
        }}

        QFrame[focusCard="true"] {{
            border: 1px solid #565656;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #171717, stop:1 #0f0f0f);
        }}

        QFrame[secondaryCard="true"] {{
            border: 1px solid {Colors.border_soft};
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #111111, stop:1 #0b0b0b);
        }}

        QFrame[collapsibleCard="true"] {{
            border: 1px solid #424242;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121212, stop:1 #0c0c0c);
        }}

        QFrame[eventCard="true"] {{
            border: 1px solid {Colors.border_soft};
            background: #0d0d0d;
        }}

        QTextEdit[eventFeed="true"] {{
            background: #090909;
            border: 1px solid #252525;
            border-radius: 8px;
            padding: 7px 8px;
        }}

        QFrame[strip="true"] {{
            background: #0d0d0d;
            border: 1px solid {Colors.border_soft};
            border-radius: 8px;
        }}

        QFrame[summaryPanel="true"] {{
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
        }}

        QFrame[metricBlock="true"] {{
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
        }}

        QFrame[tableSubcard="true"] {{
            background: #0b0b0b;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
        }}

        QFrame[actionGroup="true"] {{
            background: #0b0b0b;
            border: 1px solid #262626;
            border-radius: 8px;
        }}

        QWidget[statRow="true"] {{
            background: #0d0d0d;
            border: 1px solid #282828;
            border-radius: 8px;
        }}

        QWidget[statusMetric="true"] {{
            background: transparent;
        }}

        QPlainTextEdit {{
            background: #090909;
            border: 1px solid {Colors.border_soft};
            border-radius: 8px;
            padding: 6px;
        }}

        QFrame[near="true"] {{
            background: #121212;
            border: 1px solid #4a4a4a;
            border-radius: 8px;
        }}

        QPushButton {{
            background: {Colors.panel_high};
            border: 1px solid {Colors.border};
            border-radius: 8px;
            padding: 5px 12px;
            min-height: 30px;
            color: {Colors.text};
            font-weight: 600;
        }}

        QPushButton:hover {{
            border-color: #9a9a9a;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #262626, stop:1 #171717);
            color: #ffffff;
        }}

        QPushButton:pressed {{
            background: #101010;
            border-color: #777777;
        }}

        QPushButton:disabled {{
            background: #0d0d0d;
            border-color: {Colors.border_soft};
            color: #6f6f6f;
        }}

        QPushButton[utility="true"] {{
            min-height: 28px;
            padding: 4px 10px;
            background: #111111;
            border-color: #303030;
            color: #e6e6e6;
        }}

        QPushButton[utility="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #252525, stop:1 #161616);
            border-color: #909090;
            color: #ffffff;
        }}

        QPushButton[startAction="true"] {{
            min-height: 31px;
            padding: 5px 12px;
            background: #151515;
            border-color: #555555;
            color: #ffffff;
            font-weight: 660;
        }}

        QPushButton[startAction="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #292929, stop:1 #1b1b1b);
            border-color: #aaaaaa;
            color: #ffffff;
        }}

        QPushButton[startAction="true"]:pressed {{
            background: #111111;
            border-color: #888888;
        }}

        QPushButton[startAction="true"]:disabled {{
            background: #0f0f0f;
            border-color: #303030;
            color: #707070;
        }}

        QPushButton[startAction="true"][activeMode="true"]:disabled {{
            background: #202020;
            border-color: #9a9a9a;
            color: #eeeeee;
        }}

        QPushButton[startAction="true"][modeTone="specs"]:hover {{
            border-color: {Colors.specs};
        }}

        QPushButton[startAction="true"][modeTone="powers"]:hover {{
            border-color: {Colors.powers};
        }}

        QPushButton[startAction="true"][modeTone="specs"][activeMode="true"]:disabled {{
            background: #202020;
            border-color: {Colors.specs};
            color: #ffffff;
        }}

        QPushButton[startAction="true"][modeTone="powers"][activeMode="true"]:disabled {{
            background: #1a1a1a;
            border-color: {Colors.powers};
            color: #eeeeee;
        }}

        QPushButton[primary="true"] {{
            background: #3a3a3a;
            border-color: #a0a0a0;
            color: #ffffff;
            font-weight: 680;
        }}

        QPushButton[primary="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #555555, stop:1 #3d3d3d);
            border-color: #d0d0d0;
        }}

        QPushButton[danger="true"] {{
            background: #141414;
            border-color: #5c5c5c;
            color: #eeeeee;
        }}

        QPushButton[danger="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d2d2d, stop:1 #1b1b1b);
            border-color: #b0b0b0;
            color: #ffffff;
        }}

        QPushButton[danger="true"]:pressed {{
            background: #101010;
            border-color: #888888;
        }}

        QPushButton[danger="true"]:disabled {{
            background: #0d0d0d;
            border-color: #303030;
            color: #707070;
        }}

        QPushButton[nav="true"] {{
            text-align: left;
            min-height: 31px;
            padding: 7px 10px;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            color: {Colors.muted};
            font-weight: 600;
        }}

        QPushButton[nav="true"]:hover {{
            background: #111111;
            border-color: #303030;
            color: #ffffff;
        }}

        QPushButton[nav="true"]:checked {{
            background: #181818;
            border-color: #666666;
            color: #ffffff;
        }}

        QPushButton[chip="true"] {{
            min-height: 28px;
            padding: 4px 10px;
            background: #111111;
            border-color: #333333;
            color: {Colors.muted};
        }}

        QPushButton[chip="true"]:hover {{
            background: #202020;
            border-color: #888888;
            color: #ffffff;
        }}

        QPushButton[chip="true"]:checked {{
            background: #242424;
            border-color: {Colors.accent};
            color: #ffffff;
        }}

        QToolButton[collapsibleHeader="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141414, stop:1 #0f0f0f);
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            padding: 7px 10px;
            color: #eeeeee;
            font-weight: 650;
            text-align: left;
        }}

        QToolButton[collapsibleHeader="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222222, stop:1 #151515);
            border-color: #888888;
            color: #ffffff;
        }}

        QToolButton[collapsibleHeader="true"]:checked {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d1d1d, stop:1 #141414);
            border-color: #666666;
        }}

        QToolButton[collapsibleHeader="true"]:pressed {{
            background: #101010;
            border-color: #777777;
        }}

        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
            background: #080808;
            border: 1px solid {Colors.border};
            border-radius: 8px;
            padding: 3px 7px;
            min-height: 20px;
            color: {Colors.text};
        }}

        QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
            border-color: {Colors.accent};
        }}

        QComboBox::drop-down {{
            border: 0;
            width: 24px;
        }}

        QComboBox QAbstractItemView {{
            background: #101010;
            color: {Colors.text};
            border: 1px solid {Colors.border};
            selection-background-color: #303030;
        }}

        QCheckBox {{
            spacing: 8px;
            color: {Colors.text};
        }}

        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 4px;
            border: 1px solid {Colors.border};
            background: #0d0d0d;
        }}

        QCheckBox::indicator:checked {{
            background: {Colors.accent};
            border-color: {Colors.accent};
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: #2a2a2a;
            border-radius: 2px;
        }}

        QSlider::sub-page:horizontal {{
            background: {Colors.accent};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            background: #f6f6f6;
            border: 2px solid {Colors.accent};
            width: 14px;
            height: 14px;
            margin: -6px 0;
            border-radius: 7px;
        }}

        QTableWidget, QTableView {{
            background: #0b0b0b;
            alternate-background-color: #111111;
            border: 1px solid {Colors.border_soft};
            border-radius: 9px;
            gridline-color: #242424;
            selection-background-color: #2a2a2a;
        }}

        QHeaderView::section {{
            background: #151515;
            color: #d8d8d8;
            border: 0;
            border-bottom: 1px solid {Colors.border};
            padding: 6px 8px;
            font-weight: 650;
        }}

        QTableWidget::item {{
            padding: 3px 5px;
            border: 0;
        }}

        QTabWidget::pane {{
            border: 1px solid {Colors.border};
            border-radius: 8px;
            top: -1px;
            background: {Colors.panel};
        }}

        QTabBar::tab {{
            background: #0d0d0d;
            border: 1px solid {Colors.border_soft};
            padding: 7px 12px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            color: {Colors.muted};
            font-weight: 600;
        }}

        QTabBar::tab:selected {{
            background: {Colors.panel};
            color: #ffffff;
            border-bottom-color: {Colors.panel};
        }}

        QTextEdit, QPlainTextEdit {{
            background: #080808;
            border: 1px solid {Colors.border_soft};
            border-radius: 8px;
            padding: 7px;
            color: {Colors.text};
            font-family: Consolas, "Cascadia Mono", monospace;
            font-size: 8.8pt;
        }}

        QTextEdit {{
            line-height: 1.3em;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical {{
            background: #3a3a3a;
            border-radius: 5px;
            min-height: 32px;
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        QSplitter::handle {{
            background: #171717;
        }}
        """
    )
