import pypalmsens as ps

def find_devices():
    devices = ps.discover()
    print(devices)
    if len(devices) == 0:
        raise RuntimeError("no devices found")
    return devices

def run_measurement(dev):
    ps.connect(dev)
    
    method = ps.Method()
    res = ps.measure(method)
    
    ps.disconnect()
    return res

#def loop_methods(dev, methods, count):

#def save_method():
    
#def load_method():