from PySide6.QtWidgets import QApplication, QLabel, QWidget, QListWidget, QListWidgetItem, QMainWindow, QToolBar, QMessageBox
from PySide6.QtGui import QAction
import pypalmsens as ps

import ps_helpers as pslib
import sys

class connection_indicator(QLabel):
    def __init__(self, parent=None):
        super().__init__()
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
        try:
            self.list_widget = QListWidget(self)
            devices = pslib.find_devices()

            for i in range(len(devices)):
                dev = QListWidgetItem()
                dev.setText(str(devices[i]))
                self.list_widget.addItem(dev)
                
        except:
            self.label = QLabel(parent=self,text="Could not find any devices")
    
class main_window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Palmsens demo")

        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        scan_action = QAction("Scan devices", self)
        scan_action.setStatusTip("Scan for available devices")
        scan_action.triggered.connect(self.scan_devices)
        toolbar.addAction(scan_action)

        # disconnect_action = QAction("Disconnect", self)
        # disconnect_action.setStatusTip("Disconnect from device")
        # disconnect_action.triggered.connect(self.disconnect_device)
        #toolbar.addAction(disconnect_action)
        
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
            
    #Stub
    #def disconnect_action():
        
        
def main():
    app = QApplication(sys.argv)
    window = main_window()

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
