

import sys
import enum
from os.path import join, dirname, abspath
import queue
import serial
import serial.tools.list_ports as port_list
from qtpy import uic
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox, QAction, QDialog, QTableWidgetItem, QLabel
from pyqtgraph import PlotWidget
import pyqtgraph as pg
from collections import deque
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton

import math
import os
import scipy
import numpy as np
import random
import qtmodern.styles
import qtmodern.windows
import time
import json
import pprint

from gcodegenerator import GcodeGenerator
from dispatchers import PrimaryThread, WorkerThread, SensorThread, BipapThread, EncoderThread, BipapInitializationThread
from kalmanlib import kalman
from flowprocess import FlowProcess
from wavegenerator import WaveMapper
from startdialog import StartDialog
from portdetection import DetectDevices
from backfeed import Backfeed
from modes import MachineRunModes, BipapReturns, BipapLookup
from machinesetup import MachineSetup
from math import pi, sin
from PyQt5.QtMultimedia import *
from datalogger import DataLogger
import struct
#import RPi.GPIO as GPIO
from time import sleep
import pyautogui
from scipy.signal import butter,filtfilt
from filterlp import LowpassFilter

class StreamData(object):

    vol_base = 0.0
    deltaflow:float = 0.0
    deltaflowoffset:float = 0.0
    lungpressure:float = 0.0
    plot_run = True
    lst = []
    lines = []
    cntr = 0

    def __init__(self, step_duration):
        self.stepDuration = step_duration
        self.maxlength = 500
        self.pressure_stream = deque()
        self.flow_stream = deque()
        self.volume_stream = deque()
        self.flow_filt_stream = deque()
        self.vol_filt_stream = deque()
        self.ttm = 0.0
        self.tfdata = deque()
        self.lpf = LowpassFilter()
        self.filtered = []
        self.lungpressure = 0.0
        self.deltaflow = 0.0
        self.volume = 0.0
        self.involume = 0.0
        self.exvolume = 0.0
        self.peaks = []
        self.props = []

    def push(self, data_stream):
        
        if not self.plot_run:
            return
        self.lines = data_stream.split('\n')
        pprint.pprint(self.lines)
        if len(self.lines) > 0:
            for line in self.lines:
                self.lst = line.split(',')
                if len(self.lst) >= 5:
                    try:
                        self.lungpressure = float(self.lst[0])
                        self.deltaflow = float(self.lst[2])
                        self.volume = float(self.lst[3])
                        self.involume = float(self.lst[5])
                        self.exvolume = float(self.lst[6])
                        self.pressure_stream.append(self.lungpressure)
                        self.flow_stream.append(self.deltaflow)
                        self.volume_stream.append(self.volume)

                        if len(self.pressure_stream) > self.maxlength:
                            self.pressure_stream.popleft()
                            self.flow_stream.popleft()
                            self.flow_filt_stream = self.lpf.butter_lowpass_filter(self.flow_stream, cutoff=10, fs=40, order=1)

                            self.filtered = self.lpf.butter_lowpass_filter(self.pressure_stream, cutoff=79, fs=20, order=1)
                            ##self.peaks, self.props = scipy.signal.find_peaks(prominence=1, width=1.0)

                            self.volume_stream.popleft()
                            self.vol_filt_stream = self.lpf.butter_lowpass_filter(self.volume_stream, cutoff=79, fs=20, order=1)

                        if len(self.tfdata) < self.maxlength:
                            self.ttm += self.stepDuration
                            self.tfdata.append(self.ttm)

                    except Exception as e:
                        print(data_stream + ' : ' + str(e))

                    if self.cntr < 10:
                        self.cntr += 1
                    else:
                        self.cntr = 0
                        #print('{:f} :: {:f}'.format(self.lungpressure, self.deltaflow))
                else:
                    pass #print('sensor data stream length missmatch : ' + str(len(self.lst)))
