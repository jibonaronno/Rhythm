import sys
import serial
import pprint
import time
import enum
import queue
from queue import Queue
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt, QMutex
from collections import deque

class SignalDetector(object):
    def __init__(self, func=None):
        self.func = func
        self.maxLen = 300
        self.dque = deque()
        self.deriv_points = deque()
        self.edge = 0.0
        self.first_negative = False
        self.peak_value = 0

    def Append(self, element):
        if len(self.dque) > self.maxLen:
            self.dque.popleft()
        if len(self.deriv_points) > 6:
            self.deriv_points.popleft()
        if type(element) is float:
            self.dque.append(element)
            self.deriv_points.append(element)

    def Cycle(self, element):
        self.Append(element)
        if len(self.deriv_points) >= 6:
            self.edge = (((self.deriv_points[5] + self.deriv_points[4])/2) - ((self.deriv_points[0] + self.deriv_points[1])/2)) / 0.2
        
        if not self.first_negative:
            if self.edge < -1:
                self.peak_value = self.deriv_points[2] # element
                self.first_negative = True
                if self.func:
                    self.func()
        elif self.edge > 1:
            self.first_negative = False
