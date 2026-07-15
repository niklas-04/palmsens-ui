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
    border-radius: 6px;
}

QFrame#auroraStepCard[stepType="tag"] {
    border-left: 5px solid #64748b;
}

QFrame#auroraStepCard[stepType="open_circuit_voltage"] {
    border-left: 5px solid #0f766e;
}

QFrame#auroraStepCard[stepType="wait"] {
    border-left: 5px solid #0891b2;
}

QFrame#auroraStepCard[stepType="temperature"] {
    border-left: 5px solid #dc2626;
}

QFrame#auroraStepCard[stepType="constant_current"] {
    border-left: 5px solid #2563eb;
}

QFrame#auroraStepCard[stepType="constant_voltage"] {
    border-left: 5px solid #7c3aed;
}

QFrame#auroraStepCard[stepType="voltage_scan"] {
    border-left: 5px solid #c2410c;
}

QFrame#auroraStepCard[stepType="impedance_spectroscopy"] {
    border-left: 5px solid #be123c;
}

QFrame#auroraStepCard[stepType="loop"] {
    border-left: 5px solid #ca8a04;
}

QFrame#auroraStepCard[selected="true"] {
    background: #edf6ff;
    border-top-color: #76a7ce;
    border-right-color: #76a7ce;
    border-bottom-color: #76a7ce;
}

QFrame#auroraStepCard[selected="true"] QLabel#auroraStepIndex {
    background: #2f6f9f;
    color: #ffffff;
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
    border-radius: 4px;
    color: #49657f;
    font-size: 11px;
    font-weight: 700;
    min-width: 22px;
    padding: 2px 6px;
}

QLabel#auroraCompactFieldLabel {
    color: #52606d;
    font-size: 12px;
    padding-left: 4px;
}

QPushButton#auroraStepAction,
QPushButton#auroraAddStepButton {
    padding: 3px 8px;
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

QComboBox QAbstractItemView,
QAbstractItemView,
QListView {
    background: #ffffff;
    border: 1px solid #c7d0da;
    color: #1f2a36;
    outline: 0;
    selection-background-color: #2f6f9f;
    selection-color: #ffffff;
}

QAbstractItemView::item,
QListView::item {
    background: #ffffff;
    color: #1f2a36;
    min-height: 24px;
    padding: 4px 8px;
}

QAbstractItemView::item:hover,
QListView::item:hover {
    background: #edf3f8;
    color: #1f2a36;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d8dee6;
}
"""
