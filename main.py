from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QListWidget, QListWidgetItem, QMainWindow, QToolBar, QMessageBox, QDialog, QVBoxLayout, QPushButton
from PySide6.QtGui import QAction
from graph import graph_widget
import pypalmsens as ps

import ps_helpers as pslib
import sys

class connection_indicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_status(False) # Initierar connection som false

    def set_status(self, is_connected: bool, dev: ps.Instrument = None):
        if is_connected and dev is not None:
            self.setText(f"Connected to {dev.name}")
            self.setStyleSheet("color: green;")
        else:
            self.setText("Disconnected")
            self.setStyleSheet("color: red;")


class device_selection_dialog(QDialog):
    def __init__(self, devices, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Select Device")

        layout = QVBoxLayout(self)

        self.device_list = list_choices()
        self.device_list.set_choice(devices)
        layout.addWidget(self.device_list)

        self.connect_button = QPushButton("Connect")
        layout.addWidget(self.connect_button)

        self.selected_device = None

        self.connect_button.clicked.connect(self.select_device)

    def select_device(self):
        dev = self.device_list.get_selected_choice()
        if dev is not None:
            self.selected_device = dev
            self.accept() 

class list_choices(QWidget):
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget)
        self.choices = []
    
    def set_choice(self, choices):
        self.choices = choices
        self.list_widget.clear() # Om det fanns enheter sedan tidigare skanningar
        
        for dev in choices:
            self.list_widget.addItem(str(dev.name))
            
    def get_selected_choice(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.choices):
            return self.choices[row]
        return None
                

class device_manager(QObject):
    connected = Signal(object)
    disconnected = Signal()
    connection_changed = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self.is_connected = False
        self.device = None
        self.manager = None

    def connect_device(self, dev: ps.Instrument):
        if not self.is_connected:
            #self.manager = ps.connect(dev)
            self.device = dev
            self.is_connected = True
            self.connected.emit(dev)
            self.connection_changed.emit(True)
            
    def disconnect_device(self):
        if self.is_connected and self.device is not None:
            #self.manager.disconnect()
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

        scan_action = QAction("Connect", self)
        scan_action.setStatusTip("Scan for available devices")
        scan_action.triggered.connect(self.scan_devices)
        toolbar.addAction(scan_action)

        self.disconnect_action = QAction("Disconnect", self)
        self.disconnect_action.setStatusTip("Disconnect from device")
        self.disconnect_action.setEnabled(False) # Inte ansluten till en början
        self.disconnect_action.triggered.connect(self.device_manager.disconnect_device)
        toolbar.addAction(self.disconnect_action)

        self.connection_indicator = connection_indicator()
        self.statusBar().addPermanentWidget(self.connection_indicator)

        self.device_manager.connected.connect(self.on_connect)
        self.device_manager.disconnected.connect(self.on_disconnect)
        self.device_manager.connection_changed.connect(self.update_connection)

        self.graph = graph_widget()
        self.setCentralWidget(self.graph)
        # TODO: låt användaren plotta measurements, antingen från en metod som körs eller tex från tidigare session

    def scan_devices(self):
        try:
            devices = pslib.find_devices()
            if not devices:
                QMessageBox.warning(
                    self,
                    "Scan complete",
                    "No devices found"
                )
                return

            dialog = device_selection_dialog(devices, self)
            if dialog.exec():  # user pressed Connect
                selected = dialog.selected_device
            if selected:
                self.device_manager.connect_device(selected)
                
        except Exception as e: #TODO: Logga istället för ruta
            QMessageBox.warning(
                self,
                "Scan error",
                str(e)
            )
        
            
    def update_connection(self, is_connected: bool):
        self.disconnect_action.setEnabled(is_connected)
    
    def on_connect(self, dev):
        self.connection_indicator.set_status(True, dev)
        
    def on_disconnect(self):
        self.connection_indicator.set_status(False)

        
        
        
def main():
    app = QApplication(sys.argv)
    window = main_window()

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
