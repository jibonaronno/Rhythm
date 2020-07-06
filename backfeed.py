import sys
import serial
import pprint
import time
import enum
import queue
from queue import Queue
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt, QMutex
from timerthread import TimerThread

class Backfeed(QObject):
    feeder = Signal(str)
    def __init__(self, file):
        self.data = None
        self.array = []
        super().__init__()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timeout)
        self.gidx = 2
        self.loadFile(file)
        self.timerthread = None

    def timeout(self):
        self.feeder.emit(self.array[self.gidx])
        if(self.gidx < len(self.array)):
            self.gidx += 1
        else:
            self.gidx = 1

    def StreamDirect(self):
        for item in self.array:
            self.feeder.emit(item)

    def Start(self, time=100):
        #self.timer.start(time)
        self.timerthread.Start()

    def setCallback(self, callback, millis=100):
        if callback:
            self.feeder.connect(callback)
            self.timerthread = TimerThread(self.timeout, millis)

    def loadFile(self, file):
        with open(file, "r") as reader:
            self.data = reader.readlines()
            for line in self.data:
                self.array.append(line)
