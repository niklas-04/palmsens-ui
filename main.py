from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QListWidget, QListWidgetItem, QMainWindow, QToolBar, QMessageBox, QDialog, QVBoxLayout, QGridLayout, QPushButton, QFileDialog
from PySide6.QtGui import QAction
from graph import graph_panel
import pypalmsens as ps

import ps_helpers as pslib
import sys

PANEL_COLUMNS= 3

class connection_indicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_status(False) # Initierar connection som false

    def set_status(self, is_connected: bool, dev: pslib.discovered_device = None):
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

    def connect_device(self, dev: pslib.discovered_device):
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
        self.measurements = list()
        self.panels: list[graph_panel] = list()
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

        self.open_action = QAction("Open session", self)
        self.open_action.triggered.connect(self.open_session)
        toolbar.addAction(self.open_action)

        self.save_action = QAction("Save session", self)
        self.save_action.triggered.connect(self.save_session)
        toolbar.addAction(self.save_action)
        
        self.add_panel_action = QAction("Add panel", self)
        self.add_panel_action.triggered.connect(self.add_panel)
        toolbar.addAction(self.add_panel_action)

        self.connection_indicator = connection_indicator()
        self.statusBar().addPermanentWidget(self.connection_indicator)

        self.device_manager.connected.connect(self.on_connect)
        self.device_manager.disconnected.connect(self.on_disconnect)
        self.device_manager.connection_changed.connect(self.update_connection)
    
        self.panel_conainer = QWidget()
        self.panel_layout = QGridLayout(self.panel_conainer)
        self.setCentralWidget(self.panel_conainer)
        # TODO: låt användaren plotta measurements, antingen från en metod som körs eller tex från tidigare session

    def scan_devices(self):
        devices = pslib.find_devices()
        print(devices)
        if not devices:
            QMessageBox.warning(
                self,
                "Scan complete",
                "No devices found"
            )
            return

        dialog = device_selection_dialog(devices, self)
        if dialog.exec():
            selected = dialog.selected_device
        if selected:
            self.device_manager.connect_device(selected)
    
            
    def update_connection(self, is_connected: bool):
        self.disconnect_action.setEnabled(is_connected)
    
    def on_connect(self, dev):
        self.connection_indicator.set_status(True, dev)
        for instrument in dev.channels:
            self.add_panel(f"CH {str(instrument.channel)}")
        
    def on_disconnect(self):
        self.connection_indicator.set_status(False)
        
    def open_session(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            "",
            "Session Files (*.pssession)"
        )

        if file_path == "":
            return
        
        self.measurements = pslib.load_session(file_path)

        nr_panels = len(self.panels) # TODO: ta antal tomma paneler istället för att inte överskrida de med fyllda mätningar
        nr_measurements = len(self.measurements)
        if nr_measurements > nr_panels:
            for _ in range(nr_measurements - nr_panels):
                self.add_panel()
        for i in range(nr_measurements):
            self.panels[i].graph.plot_measurement(self.measurements[i])
            
            

    def save_session(self):
        if len(self.measurements) == 0:
            QMessageBox.warning(
                self,
                "Save error",
                "No measurements to save"
            )
            return
         
        file_path, _ = QFileDialog.getSaveFileName(
        self,
        "Save session",
        "",
        "Session Files (*.pssession)"
        )

        if file_path == "":
            return

        pslib.save_session(file_path, self.measurements)

    def add_panel(self, title="panel"):
        panel = graph_panel(title)
        self.panels.append(panel)
        panel.remove_requested.connect(lambda: self.remove_panel(panel))
        self.refresh_panel_grid()

    def remove_panel(self, panel):
        if panel not in self.panels:
            return
        
        self.panel_layout.removeWidget(panel)
        self.panels.remove(panel)
        panel.deleteLater()
        self.refresh_panel_grid()

    def refresh_panel_grid(self):
        for index, panel in enumerate(self.panels):
            row = index // PANEL_COLUMNS
            column = index % PANEL_COLUMNS
            self.panel_layout.addWidget(panel, row, column)


        
        
        
def main():
    app = QApplication(sys.argv)
    window = main_window()

    window.show()
    app.exec()


if __name__ == "__main__":
    main()
