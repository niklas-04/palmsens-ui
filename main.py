from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QListWidget, QListWidgetItem, QMainWindow, QToolBar, QMessageBox
from PySide6.QtGui import QAction
import pypalmsens as ps

import ps_helpers as pslib
import sys

class connection_indicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_status(False) # Initierar connection som false

    def set_status(self, is_connected: bool, dev:ps.Instrument = None):
        if is_connected:
            self.setText(f"Connected to {dev.name}")
            self.setStyleSheet("color: green;")
        else:
            self.setText("Disconnected")
            self.setStyleSheet("color: red;")
        

class list_devices(QLabel):
    def __init__(self):
        super().__init__()
        self.list_widget = QListWidget(self)
        devices = pslib.find_devices()

        for i in range(len(devices)):
            dev = QListWidgetItem()
            dev.setText(str(devices[i]))
            self.list_widget.addItem(dev)
                

class device_manager(QObject):
    connected = Signal(object)
    disconnected = Signal()
    connection_changed = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.device = None

    def connect_device(self, dev = None):
        if not self.is_connected:
            self.is_connected = True
            self.device = dev
            self.connected.emit(dev)
            self.connection_changed.emit(True)
            
    def disconnect_device(self):
        if self.is_connected:
            self.is_connected = False
            self.device = None
            self.disconnected.emit()
            self.connection_changed.emit(False)
    
class main_window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Palmsens demo")

        self.device_manager = device_manager()

        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        scan_action = QAction("Scan devices", self)
        scan_action.setStatusTip("Scan for available devices")
        scan_action.triggered.connect(self.scan_devices)
        toolbar.addAction(scan_action)

        self.disconnect_action = QAction("Disconnect", self)
        self.disconnect_action.setStatusTip("Disconnect from device")
        self.disconnect_action.setEnabled(False) # Inte ansluten till en början
        self.disconnect_action.triggered.connect(self.device_manager.disconnect_device)
        toolbar.addAction(self.disconnect_action)

        self.widget_connection_indicator = connection_indicator()
        self.setCentralWidget(self.widget_connection_indicator)

        self.device_manager.connected.connect(self.on_connect)
        self.device_manager.disconnected.connect(self.on_disconnect)
        self.device_manager.connection_changed.connect(self.update_connection)

    def scan_devices(self):
        try:
            devices = pslib.find_devices()
            QMessageBox.information(
                self,
                "Scan complete",
                f"Found {len(devices)} device(s)"
            )
        except:
            QMessageBox.warning(
                self,
                "Scan complete",
                "No devices found"
            )
            
    def update_connection(self, is_connected: bool):
        self.disconnect_action.setEnabled(is_connected)
    
    def on_connect(self, dev):
        self.widget_connection_indicator.set_status(True, dev)
        
    def on_disconnect(self):
        self.widget_connection_indicator.set_status(False)

        
        
        
def main():
    app = QApplication(sys.argv)
    window = main_window()

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
