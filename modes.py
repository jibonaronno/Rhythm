
import enum

class MachineRunModes(enum.Enum):
    CMV = 1
    BiPAP = 2
    CPAP = 3

class BipapReturns(enum.Enum):
    Continue = 1
    Stop = 2

class BipapLookup(object):
    def __init__(self):
        self.ipap = 8
    
    def setIpap(self, ipap):
        self.ipap = ipap

    def lookUp(self, pressure):
        if pressure > self.ipap:
            return BipapReturns.Stop
        else:
            return BipapReturns.Continue
