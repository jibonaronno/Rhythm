
import sys
import serial
import pprint
import time
import enum
import queue
from queue import Queue
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt, QMutex

class TimerThread(QObject):
    signal = Signal(str)
    def __init__(self, callback, milis):
        super().__init__()
        self.milis = milis
        self.signal.connect(callback)
        self.thread = QThread()
        self.timer = QTimer()
        #self.timer.timeout.connect(self.timeout)
        #self.timer.start(milis)
        self.thread.started.connect(self.init)

    def Start(self):
        self.thread.start()

    @Slot()
    def init(self):
        self.timer.timeout.connect(self.timeout)
        self.timer.start(self.milis)

    def timeout(self):
        self.signal.emit("tick")
