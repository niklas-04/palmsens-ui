import pypalmsens as ps
from pathlib import Path

class fake_device: #TODO:kom på bättre sätt för att testa
    def __init__(self):
        self.baudrate = 9600

    def ToString(self):
        return "MyDeviceCH01"

    def Open(self):
        pass

    async def OpenAsync(self):
        pass

def find_devices():
    # devices = ps.discover()
    # print(devices)
    # if len(devices) == 0:
    #     raise RuntimeError("no devices found")
    # return devices
    dev1 = ps.Instrument(id="MyDevice", interface="serial", device=fake_device())
    dev1.name = "Hej"
    return [dev1]

def run_measurement(dev):
    # ps.connect(dev) Persistent connection eller endast under measurement?
    
    method = ps.MethodScript()
    res = ps.measure(method)
    
    # ps.disconnect()
    return res

#def loop_methods(dev, methods, count):

def save_session(path: str | Path, session):
    ps.save_session_file(path, session)

def load_session(path: str | Path):
    return ps.load_session_file(path)
    

#def save_method():
    
#def load_method():

