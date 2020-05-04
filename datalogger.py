
import sys
from os.path import join, dirname, abspath
from machinesetup import MachineSetup
import pprint

class DataLogger(object):
    def __init__(self, filename="log.txt"):
        self.filename = filename

    def writeBlock(self, datalist):
        combined = ""
        if len(datalist) > 0:
            for data in datalist:
                combined += data + "\n"
        with open(self.filename, "a+") as writer:
            writer.write(combined)
