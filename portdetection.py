
import sys
from os.path import join, dirname, abspath
import serial
#import serial.tools.list_ports as port_list
#from serial.tools import *
from qtpy import uic
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt
from qtpy.QtWidgets import QApplication, QMainWindow, QMessageBox, QAction, QDialog, QTableWidgetItem
from pyqtgraph import PlotWidget
import pyqtgraph as pg
from collections import deque
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox

import math
import os
import numpy as np
import random
import qtmodern.styles
import qtmodern.windows
import time
import json
import pprint

from gcodegenerator import GcodeGenerator
from dispatchers import PrimaryThread, WorkerThread, SensorThread, BipapThread
from wavegenerator import WaveMapper
from startdialog import StartDialog
from math import pi, sin
from PyQt5.QtMultimedia import *
import struct
#import RPi.GPIO as GPIO
from time import sleep

class DetectDevices(object):
    def __init__(self):
        self.ports = []
        self.selected_ports = []

    def listPorts(self):
        from serial.tools.list_ports import comports
        self.ports = list(comports())
        return self.ports

    def automatePorts(self):
        from serial.tools.list_ports import comports
        self.ports = list(comports())
        for port in self.ports:
            for itm in port:
                if "USB" in itm or "ACM" in itm:
                    self.selected_ports.append(port)
        xlines = []
        if len(self.selected_ports) > 1:
            try:
                uart = serial.Serial(self.selected_ports[1][0], baudrate=115200, timeout=1)
                time.sleep(1.5)
                while uart.in_waiting:
                    line = uart.readline()
                    xlines.append(line)
                    if len(xlines) > 30:
                        break
                for line in xlines:
                    if b"Marlin" in line:
                        print(f"1. Marlin is in {self.selected_ports[1][0]}")
                        self.ComPorts['Marlin']= self.selected_ports[1][0]
                        uart.close()
                if self.ComPorts['Marlin'] == "NA":
                    self.ComPorts['Sensor'] = self.selected_ports[1][0]
                time.sleep(1)
                xlines.clear()
                uart2 = serial.Serial(self.selected_ports[0][0], baudrate=115200, timeout=1)
                time.sleep(1.5)
                while uart2.in_waiting:
                    line = uart2.readline()
                    xlines.append(line)
                    if len(xlines) > 30:
                        break
                for line in xlines:
                    if b"Marlin" in line:
                        print(f"2. Marlin is in {self.selected_ports[0][0]}")
                        uart2.close()
                        self.ComPorts['Marlin']= self.selected_ports[0][0]
                if self.ComPorts['Sensor'] == "NA":
                    self.ComPorts['Sensor'] = self.selected_ports[0][0]
                time.sleep(1)
            
            except serial.SerialException as ex:
                print("Error In SerialException - aumatePorts()" + str(ex.strerror))

        elif len(self.selected_ports) > 0:
            uart2 = serial.Serial(self.selected_ports[0][0], baudrate=115200, timeout=1)
            time.sleep(1.5)
            while uart2.in_waiting:
                line = uart2.readline()
                xlines.append(line)
                if len(xlines) > 30:
                    break
            for line in xlines:
                if b"Marlin" in line:
                    print(f"2. Marlin is in {self.selected_ports[0][0]}")
                    uart2.close()
                    self.ComPorts['Marlin']= self.selected_ports[0][0]
            if self.ComPorts['Marlin'] == "NA":
                self.ComPorts['Sensor'] = self.selected_ports[0][0]
            time.sleep(1)

class AutoDetectMarlin(QObject):
    def __init__(self):
        pass
