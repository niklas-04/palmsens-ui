APP_STYLESHEET = """
QMainWindow {
    background: #f4f6f8;
}

QDialog#methodConfigDialog {
    background: #eef2f6;
}

QToolBar#mainToolbar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #d8dee6;
    spacing: 6px;
    padding: 8px 10px;
}

QToolBar#mainToolbar QToolButton,
QToolBar#graphToolbar QToolButton,
QPushButton {
    background: #ffffff;
    border: 1px solid #c7d0da;
    border-radius: 7px;
    color: #243241;
    padding: 6px 12px;
}

QToolBar#mainToolbar QToolButton:hover,
QToolBar#graphToolbar QToolButton:hover,
QPushButton:hover {
    background: #eef4fa;
    border-color: #8ca3ba;
}

QToolBar#mainToolbar QToolButton:pressed,
QToolBar#graphToolbar QToolButton:pressed,
QPushButton:pressed {
    background: #dce8f3;
}

QToolButton:disabled {
    color: #8a96a3;
    background: #f5f7f9;
    border-color: #d8dee6;
}

QWidget#panelContainer {
    background: #f4f6f8;
}

QFrame#graphPanel {
    background: #ffffff;
    border: 1px solid #d8dee6;
    border-radius: 8px;
}

QFrame#auroraSection,
QFrame#auroraStepCard,
QFrame#auroraOptionsCard {
    background: #ffffff;
    border: 1px solid #d8dee6;
    border-radius: 12px;
}

QFrame#auroraStepCard {
    border-color: #e4ebf2;
    border-radius: 10px;
}

QLabel#graphPanelTitle {
    color: #1f2a36;
    font-size: 14px;
    font-weight: 700;
}

QLabel#auroraSectionTitle,
QLabel#auroraStepTitle,
QLabel#auroraCardTitle {
    color: #1f2a36;
    font-size: 13px;
    font-weight: 700;
}

QLabel#auroraStepSummary,
QLabel#auroraCardDescription,
QLabel#auroraHelpText,
QLabel#auroraSectionDescription,
QLabel#auroraSequenceMeta,
QLabel#auroraFieldHint {
    color: #52606d;
}

QLabel#auroraStepIndex {
    background: #edf3f8;
    border: 0;
    border-radius: 9px;
    color: #49657f;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
}

QPushButton#auroraStepAction,
QPushButton#auroraAddStepButton {
    padding: 5px 10px;
}

QScrollArea#auroraStepsScroll {
    background: transparent;
    border: 0;
}

QScrollArea#auroraStepsScroll QWidget {
    background: transparent;
}

QCheckBox {
    spacing: 6px;
}

QToolBar#graphToolbar {
    background: transparent;
    border: 0;
    spacing: 4px;
}

QScrollArea#panelScrollArea {
    background: #f4f6f8;
    border: 0;
}

QLabel#connectionIndicator {
    font-weight: 600;
    padding: 2px 8px;
}

QListWidget,
QComboBox,
QLineEdit {
    background: #ffffff;
    border: 1px solid #c7d0da;
    border-radius: 7px;
    padding: 6px 8px;
    selection-background-color: #2f6f9f;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d8dee6;
}
"""
