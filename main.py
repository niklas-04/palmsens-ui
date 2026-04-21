from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget, QListWidget, QListWidgetItem
import pypalmsens as ps
import ps_helpers as pslib
import sys

class connection_indicator(QWidget):
    def __init(self):
        self.label = QLabel()
        

class list_devices(QWidget):
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
    

def main():
    app = QApplication(sys.argv)

    app.exec()


if __name__ == "__main__":
    main()
