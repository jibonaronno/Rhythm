
import sys
from os.path import join, dirname, abspath
from machinesetup import MachineSetup
import pprint
from backfeed import Backfeed

class DataLogger(object):
    def __init__(self, filename="log4.txt"):
        self.filename = filename

    def writeBlock(self, datalist):
        combined = ""
        if len(datalist) > 0:
            for data in datalist:
                combined += data
        with open(self.filename, "a+") as writer:
            writer.write(combined)

logger = DataLogger('log4.csv')
iCount = 0
lData = []
def getStreamData(line):
    iCount = iCount
    if iCount < 10:
        iCount += 1
        if len(line > 15):
            lData.append(line)
    else:
        iCount=0
        logger.writeBlock(lData)
        lData.clear()
        if len(line > 15):
            lData.append(line)


streamer = Backfeed('log2.txt')
streamer.setCallback(getStreamData)
#streamer.Start(1)