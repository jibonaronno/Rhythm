#!/usr/bin/python3
import sys
from os.path import join, dirname, abspath
import serial
import serial.tools.list_ports as port_list
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

_UI = join(dirname(abspath(__file__)), 'VentUI.ui')


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        startdlg = StartDialog(None)
        startdlg.show()

        #self.verticalLayout_2 = QVBoxLayout()
        self.tableHeaders = ['VT', 'I:E', 'RR', 'FIO2']
        self.widget = uic.loadUi(_UI, self)
        window_title = "Rhythm"
        self.setWindowTitle(window_title)
        self.json = JsonSettings("settings.json")
        self.settings_dict = self.json.dict
        pprint.pprint(self.settings_dict)
        self.table = QTableWidget(self)
        self.table.setRowCount(2)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(self.tableHeaders)
        self.table.setItem(0,0, QTableWidgetItem(self.settings_dict[r"vt"]))
        self.table.setItem(0,1, QTableWidgetItem(self.settings_dict[r"ie"]))
        self.table.setItem(0,2, QTableWidgetItem(self.settings_dict[r"rr"]))
        self.table.setItem(0,3, QTableWidgetItem(self.settings_dict[r"fio2"]))
        #self.table.itemChanged.connect(self.SaveSettings)

        self.wave = WaveMapper()
        
        #self.vt = int(self.settings_dict[r"vt"])
        #self.rr = int(self.settings_dict[r"rr"])
        #self.ie = int(self.settings_dict[r"ie"])
        #self.fio2 = int(self.settings_dict[r"fio2"])

        self.vt = self.vtdial.value()
        self.ie = self.iedial.value()
        self.rr = self.rrdial.value()
        self.fio2 = self.fiodial.value()

        self.table.hide()
        self.verticalLayout_2.addWidget(self.table)

        self.generator = GcodeGenerator(self.vt, self.rr, self.ie, self.fio2)

        self.motion_table = QTableWidget(self)
        self.motion_table_headers = ['variables', 'values']
        self.motion_table.setColumnCount(2)
        self.motion_table.setRowCount(10)
        self.motion_table.setHorizontalHeaderLabels(self.motion_table_headers)
        self.motion_table.hide()

        self.lungpressuredata = deque()
        self.lungpressurepeakdata = deque()
        self.peeppressuredata = deque()
        self.peeppressurepeakdata = deque()

        self.lungpressure_line_pen = pg.mkPen(200, 100, 0)
        self.plotter = PlotWidget()
        self.plotter.showGrid(x=True, y=True, alpha=None)
        self.plotter.setTitle("Pressure")
        self.curve1 = self.plotter.plot(0,0,"lungpressure", 'b')
        self.curve2 = self.plotter.plot(0,0,"peakpressure", pen = self.lungpressure_line_pen)

        self.flowplotter = PlotWidget()
        self.flowplotter.showGrid(x=True, y=True, alpha=None)
        self.flowplotter.setTitle("Flow")

        self.volplotter = PlotWidget()
        self.volplotter.showGrid(x=True, y=True, alpha=None)
        self.volplotter.setTitle("Volume")
        
        #self.motion_table.setSizeAdjustPolicy(QtWidget.QAbstractScrollArea.AdjustToContents)
        self.CalculateSettings()
        self.verticalLayout_2.addWidget(self.motion_table)
        self.verticalLayout_2.addWidget(self.plotter)
        self.verticalLayout_2.addWidget(self.flowplotter)
        self.verticalLayout_2.addWidget(self.volplotter)
        self.motion_table.hide()

        self.gcodetable = QTableWidget(self)
        self.gcodetable.setRowCount(1)
        self.gcodetable.setColumnCount(1)
        #self.verticalLayout_2.addWidget(self.gcodetable)

        self.hbox = QHBoxLayout()
        #self.verticalLayout_2.addChildLayout(self.hbox)
        self.verticalLayout_2.addLayout(self.hbox)
        self.hbox.addWidget(self.gcodetable)
        self.txrxtable = QTableWidget()
        self.txrxtable.setRowCount(1)
        self.txrxtable.setColumnCount(1)
        self.gcodetable.hide()
        self.txrxtable.hide()
        self.txrxtablevisible = False
        self.hbox.addWidget(self.txrxtable)
        #self.hbox.addLayout

        self.bipap = BipapThread("", self.generator)
        self.bipapthreadcreated = False

        self.peepdial.valueChanged.connect(self.peepDialChanged)
        self.peeplcd.display(self.peepdial.value())
        self.peakdial.valueChanged.connect(self.peakDialChanged)
        self.peaklcd.display(self.peakdial.value())
        self.ipapdial.valueChanged.connect(self.ipapDialChanged)
        self.ipaplcd.display(self.ipapdial.value())
        self.vtdial.valueChanged.connect(self.vtDialChanged)
        self.vtlcd.display(self.vtdial.value())
        self.iedial.valueChanged.connect(self.ieDialChanged)
        self.ielcd.display(self.iedial.value())
        self.rrdial.valueChanged.connect(self.rrDialChanged)
        self.rrlcd.display(self.rrdial.value())
        self.fiodial.valueChanged.connect(self.fioDialChanged)
        self.fiolcd.display(self.fiodial.value())
        self.lowpdial.valueChanged.connect(self.lowpDialChanged)
        self.lowplcd.display(self.lowpdial.value())
        self.peeplcd.display(self.peepdial.value())
        self.himinitdial.valueChanged.connect(self.himinitDialChanged)
        self.himinitlcd.display(self.himinitdial.value())
        self.lowminitdial.valueChanged.connect(self.lowminitDialChanged)
        self.lowminitlcd.display(self.lowminitdial.value())
        self.alarm.hide()
        self.startpush.hide()

        self.s = ""
        self.s2 = ""
        self.ports = list(port_list.comports())

        self.primaryThreadCreated = False
        self.workerThreadCreated = False
        self.sensorThreadCreated = False
        self.serialPortOpen = False
        self.serialSensorOpen = False
        self.gengcode.hide()
        self.childrenMakeMouseTransparen()

        self.flag_sensorlimit_tx = True
        self.sensorLimitTimer = QTimer(self)
        self.sensorLimitTimer.timeout.connect(self.checkSensorLimitChanged)
        self.sensorLimitTimer.start(1000)

    def checkSensorLimitChanged(self):
        #strtx = str(self.peakdial.value()) + "," + str(self.lowpdial.value()) + "," + str(self.peepdial.value()) + "," + str(self.himinitdial.value()) + "," + str(self.lowminitdial.value()) + "\r\n"
        #self.strtx = "<peak,12," + str(self.peakdial.value()) + "> "
        #print(self.strtx)
        if self.sensorThreadCreated:
            if self.flag_sensorlimit_tx:
                self.strtx = "<peak,12," + str(self.peakdial.value()) + "> " # + "," + str(self.lowpdial.value()) + "," + str(self.peepdial.value()) + "," + str(self.himinitdial.value()) + "," + str(self.lowminitdial.value())
                self.sensor.txsensordata(self.strtx)
                self.flag_sensorlimit_tx = False


    def childrenMakeMouseTransparen(self):
        self.label_13.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.vtlcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.ilcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.ielcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.rrlcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.fiolcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_15.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_17.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_14.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_16.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.peaklcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.peeplcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lowplcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lowminitlcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.himinitlcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def update_param_table(self):
        self.table.setItem(0,0, QTableWidgetItem(self.settings_dict[r"vt"]))
        self.table.setItem(0,1, QTableWidgetItem(self.settings_dict[r"ie"]))
        self.table.setItem(0,2, QTableWidgetItem(self.settings_dict[r"rr"]))
        self.table.setItem(0,3, QTableWidgetItem(self.settings_dict[r"fio2"]))

    def peepDialChanged(self):
        self.peeplcd.display(self.peepdial.value())
        self.flag_sensorlimit_tx = True

    def peakDialChanged(self):
        self.peaklcd.display(self.peakdial.value())
        self.flag_sensorlimit_tx = True

    def lowpDialChanged(self):
        self.lowplcd.display(self.lowpdial.value())
        self.flag_sensorlimit_tx = True

    def himinitDialChanged(self):
        self.himinitlcd.display(self.himinitdial.value())
        self.flag_sensorlimit_tx = True

    def lowminitDialChanged(self):
        self.lowminitlcd.display(self.lowminitdial.value())
        self.flag_sensorlimit_tx = True

    def ipapDialChanged(self):
        self.ipaplcd.display(self.ipapdial.value())
        self.flag_sensorlimit_tx = True

    def vtDialChanged(self):
        self.vtlcd.display(self.vtdial.value())
        self.vt = self.vtdial.value()
        self.settings_dict[r"vt"] = str(self.vt)
        self.update_param_table()
        self.SaveSettings()

    def ieDialChanged(self):
        self.table.setItem(0,1, QTableWidgetItem(self.settings_dict[r"ie"]))
        self.ielcd.display(self.iedial.value())
        self.ie = self.iedial.value()
        self.settings_dict[r"ie"] = str(self.ie)
        self.update_param_table()
        self.SaveSettings()

    def rrDialChanged(self):
        self.rrlcd.display(self.rrdial.value())
        self.rr = self.rrdial.value()
        self.settings_dict[r"rr"] = str(self.rr)
        self.update_param_table()
        self.SaveSettings()

    def fioDialChanged(self):
        self.fiolcd.display(self.fiodial.value())
        self.fio2 = self.fiodial.value()
        self.settings_dict[r"fio2"] = str(self.fio2)
        self.update_param_table()
        self.SaveSettings()

    
    def ShowGcodeTable(self):
        codelist = self.generator.gcodestr.splitlines()
        rowcount = len(codelist)
        self.gcodetable.setRowCount(rowcount)
        self.gcodetable.setColumnCount(1)
        for i in range(rowcount):
            self.gcodetable.setItem(i, 0, QTableWidgetItem(codelist[i]))

    def CalculateSettings(self):
        del self.generator
        ###self.json = JsonSettings("settings.json")
        ###self.settings_dict = self.json.dict
        #self.vt = int(self.settings_dict[r"vt"])
        #self.rr = int(self.settings_dict[r"rr"])
        #self.ie = int(self.settings_dict[r"ie"])
        #self.fio2 = int(self.settings_dict[r"fio2"])
        self.generator = GcodeGenerator(self.vt, self.rr, self.ie, self.fio2)
        self.generator.GenerateCMV()
        self.motion_table.setItem(0,0, QTableWidgetItem('Dp'))
        self.motion_table.setItem(0,1, QTableWidgetItem(str(self.generator.Dp)))
        self.motion_table.setItem(1,0, QTableWidgetItem('Dr'))
        self.motion_table.setItem(1,1, QTableWidgetItem(str(self.generator.Dt)))
        self.motion_table.setItem(2,0, QTableWidgetItem('Dt'))
        self.motion_table.setItem(2,1, QTableWidgetItem(str(self.generator.Dt)))
        self.motion_table.setItem(3,0, QTableWidgetItem('Ti'))
        self.motion_table.setItem(3,1, QTableWidgetItem(str(self.generator.Ti)))
        self.motion_table.setItem(4,0, QTableWidgetItem('Th'))
        self.motion_table.setItem(4,1, QTableWidgetItem(str(self.generator.Th)))
        self.motion_table.setItem(5,0, QTableWidgetItem('Vi'))
        self.motion_table.setItem(5,1, QTableWidgetItem(str(self.generator.Vi)))
        self.motion_table.setItem(6,0, QTableWidgetItem('Vh'))
        self.motion_table.setItem(6,1, QTableWidgetItem(str(self.generator.Vh)))

    def LungSensorData(self, data_stream):
        #print(data_stream.split(','))
        lst = data_stream.split(",")
        self.maxLen = 100  # max number of data points to show on graph
        if(len(lst) > 1):
            try:
                if len(self.lungpressuredata) > self.maxLen:
                    self.lungpressuredata.popleft()  # remove oldest
                if len(self.lungpressurepeakdata) > self.maxLen:
                    self.lungpressurepeakdata.popleft()
                self.lungpressurepeakdata.append(float(self.peakdial.value()))
                self.lungpressuredata.append(float(lst[0]) + float(self.peepdial.value()))
                self.curve1.setData(self.lungpressuredata)
                self.curve2.setData(self.lungpressurepeakdata)
            except:
                pass
            else:
                if (float(lst[1]) + float(self.peepdial.value())) > self.peakdial.value():
                    if self.sensorThreadCreated:
                        self.sensor.beep()

    def peepSensorData(self, data_stream):
        #print(data_stream.split(','))
        lst = data_stream.split(",")
        self.maxLen = 100  # max number of data points to show on graph
        if(len(lst) > 1):
            try:
                if len(self.peeppressuredata) > self.maxLen:
                    self.peeppressuredata.popleft()  # remove oldest
                self.peeppressuredata.append(float(lst[1]) + float(self.peepdial.value()))
                self.curve1.setData(self.peeppressuredata)
            except:
                pass
            else:
                if (float(lst[1]) + float(self.peepdial.value())) > self.peakdial.value():
                    if self.sensorThreadCreated:
                        self.sensor.beep()

    def write_info(self, data_stream):
        rcount = self.txrxtable.rowCount()
        self.txrxtable.insertRow(rcount)
        self.txrxtable.setItem(rcount,0, QTableWidgetItem(data_stream))
        self.txrxtable.scrollToBottom()
        self.txrxtable.resizeColumnsToContents()
        self.txrxtable.resizeRowsToContents()
        if data_stream == "StoppedOK":
            if self.primaryThreadCreated:
                self.primaryThread.exit()
                self.primaryThread.wait()
                self.primaryThreadCreated = False
                del self.primaryThread
                self.runloop.setEnabled(True)

    @Slot()
    def on_gengcode_clicked(self):
        self.CalculateSettings()
        self.generator.GenerateCMV()
        print(self.generator.gcodeprimary)
        self.ShowGcodeTable()

    @Slot()
    def on_scanPorts_clicked(self):
        self.ports = list(port_list.comports())
        self.widget.portsList.clear()
        self.widget.monitoringPort.clear()
        print(len(self.ports))
        for p in self.ports:
            self.widget.portsList.addItem(p[0])
            self.widget.monitoringPort.addItem(p[0])

    @Slot()
    def on_btninit_clicked(self):
        if not self.workerThreadCreated:
            if not self.primaryThreadCreated:
                self.primary = PrimaryThread(self.s, self.generator)
                self.primaryThread = QThread()
                self.primaryThread.started.connect(self.primary.run)
                self.primary.signal.connect(self.write_info)
                self.primary.moveToThread(self.primaryThread)
                self.primaryThread.start()
                self.primaryThreadCreated = True
                print("Starting Primary Thread")
        if self.serialSensorOpen:
            if not self.sensorThreadCreated:
                self.sensor = SensorThread(self.s2)
                self.sensorThread = QThread()
                self.sensorThread.started.connect(self.sensor.run)
                self.sensor.signal.connect(self.LungSensorData)
                self.sensor.moveToThread(self.sensorThread)
                self.sensorThread.start()
                self.sensorThreadCreated = True
                print("Starting Sensor Thread ...")

    @Slot()
    def on_runloop_clicked(self):
        if not self.primaryThreadCreated:
            if not self.workerThreadCreated:
                self.worker = WorkerThread(self.s, self.generator)
                self.workerThread = QThread()
                self.workerThread.started.connect(self.worker.run)
                self.worker.signal.connect(self.write_info)
                self.worker.moveToThread(self.workerThread)
                self.workerThread.start()
                self.workerThreadCreated = True
                print("Starting Worker Thread")

    @Slot()
    def on_disconnect_clicked(self):
        if self.serialPortOpen:
            if self.workerThreadCreated:
                self.worker.Stop()
                self.workerThread.exit()
                self.workerThread.wait()
                self.workerThreadCreated = False
                del self.workerThread
            if self.primaryThreadCreated:
                self.primaryThread.exit()
                self.primaryThread.wait()
                self.primaryThreadCreated = False
                del self.primaryThread
            if self.sensorThreadCreated:
                self.sensor.Stop()
                self.sensorThread.exit()
                self.sensorThread.wait()
                self.sensorThreadCreated = False
            self.s.close()
            if self.serialSensorOpen:
                self.s2.close()
            self.serialPortOpen = False
            self.serialSensorOpen = False
            self.connect.setEnabled(True)
            self.disconnect.setEnabled(False)
            self.runloop.setEnabled(False)
            self.btninit.setEnabled(False)

    @Slot()
    def on_btnalarmpage_clicked(self):
        #self.stackedWidget = QStackerWidget()
        if self.btnalarmpage.isChecked():
            self.stackedWidget.setCurrentIndex(1)
        else:
            self.stackedWidget.setCurrentIndex(0)

    @Slot()
    def on_startpush_clicked(self):
        if not self.bipapthreadcreated:
            self.bipapThread = QThread()
            self.bipapThread.started.connect(self.bipap.run)
            #self.bipap.signal.connect(self...)
            self.bipap.moveToThread(self.bipapThread)
            self.bipapThread.start()
            self.bipapthreadcreated = True
            print("Bipap Thread Created")
        self.bipap.StartMoving()

    @Slot()
    def on_connect_clicked(self):
        try:
            if not self.serialPortOpen:
                print("Serial Port Name : " + self.portsList.currentText())
                self.s = serial.Serial(self.portsList.currentText(), baudrate=115200, timeout=1)
                #self.s.open()
                time.sleep(1)
                self.serialPortOpen = True
                #self.s.write("\r\n\r\n") # Hit enter a few times to wake the Printrbot
                #time.sleep(2)   # Wait for Printrbot to initialize
                while self.s.in_waiting:
                    self.s.readline()
                    #print(self.s.readline().decode("ascii"))
                #self.s.flushInput()  # Flush startup text in serial input
                #monitoringPort
            if self.portsList.currentText() != self.monitoringPort.currentText():
                if not self.serialSensorOpen:
                    self.s2 = serial.Serial(self.monitoringPort.currentText(), baudrate=115200, timeout=1)
                    self.serialSensorOpen = True
            
        except serial.SerialException as ex:
            self.serialPortOpen = False
            print(ex.strerror)
            print("Error Opening Serial Port..........................................")
        else:
            self.connect.setEnabled(False)
            self.disconnect.setEnabled(True)
            self.btninit.setEnabled(True)

    @Slot()
    def on_gcodeshow_clicked(self):
        if self.txrxtablevisible:
            self.txrxtable.hide()
            self.txrxtablevisible = False
        else:
            self.txrxtablevisible = True
            self.txrxtable.show()
        #self.wave.BeepBeep()
        #self.wave.changeFrequency(1000)
        #self.wave.changeVolume(1000)
        #self.wave.play()

    def SaveSettings(self):
        ###self.json = JsonSettings("settings.json")
        ###self.settings_dict = self.json.dict
        self.json.dict[r'vt'] = str(self.vt)
        self.json.dict[r'ie'] = str(self.ie)
        self.json.dict[r'rr'] = str(self.rr)
        self.json.dict[r'fio2'] = str(self.fio2)
        self.generator = GcodeGenerator(self.vt, self.rr, self.ie, self.fio2)
        self.generator.GenerateCMV()
        if self.workerThreadCreated:
            self.worker.updateGcode(self.generator)
        pprint.pprint(self.generator.gcodestr)
        #self.json.dumptojson()
        ###self.vt = int(self.settings_dict[r"vt"])
        ###self.rr = int(self.settings_dict[r"rr"])
        ###self.ie = int(self.settings_dict[r"ie"])
        ###self.fio2 = int(self.settings_dict[r"fio2"])
        self.CalculateSettings()
        ###print(str(self.vt) + ", "+str(self.ie)+", "+str(self.rr)+", "+str(self.fio2)+"\r\n")
        ###pprint.pprint(self.json.dict)

    @Slot()
    def on_alarm_clicked(self):
        self.wave.playstart()

class JsonSettings(object):
    def __init__(self , location):
        self.location = os.path.expandvars(location)
        #print(self.location)
        self.load(self.location)
        #pprint.pprint(self.db[r'Columns'])
    def load(self , location):
        if os.path.exists(location):
            self._load()
        else:
            print("location missing")
            self.dict = {}
        return True
    def dumptojson(self):
        try:
            json.dump(self.dict , open(self.location, "w+"))
            return True
        except:
            return False

    def _load(self):
        self.dict = json.load(open(self.location , "r"))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    qtmodern.styles.dark(app)
    #qtmodern.styles.light(app)

    mw_class_instance = MainWindow()
    mw = qtmodern.windows.ModernWindow(mw_class_instance)
    mw.show()
    sys.exit(app.exec_())
