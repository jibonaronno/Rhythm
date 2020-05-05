#!/usr/bin/python3
import sys
from os.path import join, dirname, abspath
import queue
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
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton

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
from dispatchers import PrimaryThread, WorkerThread, SensorThread, BipapThread, BipapInitializationThread
from kalmanlib import kalman
from flowprocess import FlowProcess
from wavegenerator import WaveMapper
from startdialog import StartDialog
from modes import MachineRunModes, BipapReturns, BipapLookup
from machinesetup import MachineSetup
from math import pi, sin
from PyQt5.QtMultimedia import *
from datalogger import DataLogger
import struct
#import RPi.GPIO as GPIO
from time import sleep

_UI = join(dirname(abspath(__file__)), 'VentUI.ui')

class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        startdlg = StartDialog(None)
        
        self.tableHeaders = ['VT', 'I:E', 'RR', 'FIO2']
        self.widget = uic.loadUi(_UI, self)
        window_title = "Rhythm"
        self.setWindowTitle(window_title)
        self.json = JsonSettings("settings.json")
        self.settings_dict = self.json.dict
        pprint.pprint(self.settings_dict)

        self.wave = WaveMapper()
        
        # Setting up Runmode for BiPAP. Call a cyclic function in LungSensorData(...) BipapLookup.lookUp(pressure)
        # This function will return BipapReturns.Continue or BipapReturns.Stop
        self.runMode = MachineRunModes.CMV
        self.ipap = 15.0
        self.bipapReturns = BipapReturns.Continue
        self.bipapLookup = BipapLookup()
        self.lst = []

        self.vt = self.vtdial.value()
        self.ie = self.iedial.value()
        self.rr = self.rrdial.value()
        self.fio2 = self.fiodial.value()

        self.generator = GcodeGenerator(self.vt, self.rr, self.ie, self.fio2)

        self.loadMachineSetup(self.generator)

        self.lungpressuredata = deque()
        self.lungpressurepeakdata = deque()
        self.peeppressuredata = deque()
        self.peeppressurepeakdata = deque()
        self.kalmandata = deque()
        self.voldata = deque()
        self.sumofvolume = 0.0

        self.dvdata = deque()
        self.deriv_points = deque()
        self.timesnap = 0.0
        self.tic = 0.0

        self.lungpressure_line_pen = pg.mkPen(200, 100, 0)
        self.plotter = PlotWidget()
        self.plotter.showGrid(x=True, y=True, alpha=None)
        self.plotter.setTitle("Pressure")
        self.curve1 = self.plotter.plot(0,0,"lungpressure", 'b')
        self.curve2 = self.plotter.plot(0,0,"peakpressure", pen = self.lungpressure_line_pen)
        self.kalmanpen = pg.mkPen(20, 100, 20)
        self.curve3 = self.plotter.plot(0,0, "kalman", pen = self.kalmanpen)

        self.derivative_pen = pg.mkPen(200, 200, 10)
        self.derivative_pen_in = pg.mkPen(10, 200, 10)
        self.derivative_pen_out = pg.mkPen(10, 200, 200)
        #self.dvcurve = self.plotter.plot(0,0,"dvcurve", pen = self.derivative_pen)

        self.inhale_t_count = 0
        self.inhale_t = 0
        self.exhale_t = 0
        self.exhale_t_count = 0
        self.flag_idle = True
        self.idle_count = 0

        #self.dvcurve.setPen()

        self.flowplotter = PlotWidget()
        self.flowplotter.showGrid(x=True, y=True, alpha=None)
        self.flowplotter.setTitle("Flow")

        self.dvcurve = self.flowplotter.plot(0,0,"dvcurve", pen = self.derivative_pen)

        self.volplotter_pen = pg.mkPen(200, 20, 10)
        self.volplotter = PlotWidget()
        self.volplotter.showGrid(x=True, y=True, alpha=None)
        self.volplotter.setTitle("Volume")
        self.volcurve = self.volplotter.plot(0,0,"volcurve", self.volplotter_pen)
        
        ###self.CalculateSettings()
        self.verticalLayout_2.addWidget(self.plotter)
        self.verticalLayout_2.addWidget(self.flowplotter)
        self.verticalLayout_2.addWidget(self.volplotter)
        #self.flowplotter.hide()
        #self.volplotter.hide()

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

        self.flowprocess = FlowProcess()

        #self.bipap = BipapThread("", self.generator)
        self.pressureque = queue.Queue()
        self.bipap_init_threadcreated = False
        self.bipapthreadcreated = False

        self.modecombobox.currentIndexChanged.connect(self.modeselectionchanged)
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
        #self.alarm.hide()
        self.startpush.hide()
        self.btnhault.hide()
        self.portsList.hide()
        self.monitoringPort.hide()
        self.scanPorts.hide()

        self.kalman = kalman()

        #self.vtdial.setStyleSheet("{ background-color: rgb(20,20,20) }")

        self.serialMarlin = ""
        self.serialSensor = ""
        self.ports = list(port_list.comports())

        self.bipapthreadcreated = False

        self.primaryThreadCreated = False
        self.workerThreadCreated = False
        self.sensorThreadCreated = False
        self.marlinPortOpen = False
        self.sensorPortOpen = False
        self.gengcode.hide()
        self.childrenMakeMouseTransparen()

        self.datalogger = DataLogger()
        self.log_interval_count = 0

        self.flag_sensorlimit_tx = True
        self.sensorLimitTimer = QTimer(self)
        self.sensorLimitTimer.timeout.connect(self.checkSensorLimitChanged)

        self.modecombobox.addItem("CMV")
        self.modecombobox.addItem("BiPAP")

        self.ComPorts = {'Marlin':'NA', 'Sensor':'NA'}
        self.selected_ports = []

        self.automatePorts()
        pprint.pprint(self.ComPorts)

        if self.ComPorts['Sensor'] == 'NA':
            self.showdialog("Sensor Controller")

        if self.ComPorts['Marlin'] == 'NA':
            self.showdialog("Motion Controller")
        else:
            self.autoConnect()
            
        self.sensorLimitTimer.start(1000)

    def showdialog2(self, msg):
        d = QDialog()
        b1 = QPushButton("ok",d)
        b1.move(50,50)
        d.setWindowTitle(msg)
        d.setWindowModality(Qt.ApplicationModal)
        d.exec_()

    def showdialog(self, msgstr):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(msgstr + "Controller Not Connected")
        msg.setInformativeText(msgstr + "Controller Not Connected")
        msg.setWindowTitle("Controller Error")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    def loadMachineSetup(self, generator):
        self.t_acc.setText(str(generator.ACC))
        self.t_xmax.setText(str(generator.xmax))
        self.t_xamb.setText(str(generator.xamb))
        self.t_xrect.setText(str(generator.xrect))
        self.t_xconoffset.setText(str(generator.xcon_offset))
        self.t_vtmax.setText(str(generator.vtmax))

    # @Slot()
    # def on_btncmv_clicked(self):
    #     self.buttonstack.setCurrentIndex(0)
    #     pass

    # @Slot()
    # def on_btnbipap_clicked(self):
    #     self.buttonstack.setCurrentIndex(1)
    #     pass

    @Slot()
    def on_btninitbipap_clicked(self):
        if self.sensorPortOpen:
            if not self.sensorThreadCreated:
                self.sensor = SensorThread(self.serialSensor, self.pressureque)
                self.sensorThread = QThread()
                self.sensorThread.started.connect(self.sensor.run)
                self.sensor.signal.connect(self.LungSensorData)
                self.sensor.moveToThread(self.sensorThread)
                self.sensorThread.start()
                self.sensorThreadCreated = True
                print("Starting Sensor Thread ...")
        if not self.bipap_init_threadcreated:
            if not self.bipapthreadcreated:
                self.bipapinit = BipapInitializationThread(self.serialMarlin, self.generator, self.pressureque)
                self.bipapinitThread = QThread()
                self.bipapinitThread.started.connect(self.bipapinit.run)
                self.bipapinit.signal.connect(self.write_info)
                self.bipapinit.ppsignal.connect(self.endBipap)
                self.bipapinit.moveToThread(self.bipapinitThread)
                self.bipapinitThread.start()
                self.bipap_init_threadcreated = True
                print("Starting bipap_init Thread")

    @Slot()
    def on_btnmachinesetup_clicked(self):
        self.stackedWidget.setMinimumHeight(230)
        self.stackedWidget.setCurrentIndex(3)

    @Slot()
    def on_btnsavemachinesetup_clicked(self):
        self.generator.ACC = int(self.t_acc.text())
        self.generator.xmax = int(self.t_xmax.text())
        self.generator.xamb = int(self.t_xamb.text())
        self.generator.xrect = int(self.t_xrect.text())
        self.generator.xcon_offset = int(self.t_xconoffset.text())
        self.generator.vtmax = int(self.t_vtmax.text())
        self.generator.machinesetup.save()

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
                self.primary = PrimaryThread(self.serialMarlin, self.generator)
                self.primaryThread = QThread()
                self.primaryThread.started.connect(self.primary.run)
                self.primary.signal.connect(self.write_info)
                self.primary.moveToThread(self.primaryThread)
                self.primaryThread.start()
                self.primaryThreadCreated = True
                print("Starting Primary Thread")
        if self.sensorPortOpen:
            if not self.sensorThreadCreated:
                self.sensor = SensorThread(self.serialSensor, self.pressureque)
                self.sensorThread = QThread()
                self.sensorThread.started.connect(self.sensor.run)
                self.sensor.signal.connect(self.LungSensorData)
                self.sensor.moveToThread(self.sensorThread)
                self.sensorThread.start()
                self.sensorThreadCreated = True
                print("Starting Sensor Thread ...")

    
    @Slot()
    def on_btnrunbploop_clicked(self):
        pprint.pprint(self.pparr)
        self.generator.GenerateBiPAP(self.pparr, self.ipapdial.value())
        print(self.generator.gcodestr)
        if not self.primaryThreadCreated:
            if not self.workerThreadCreated:
                self.worker_cmd_que = queue.Queue()
                self.worker = WorkerThread(self.serialMarlin, self.generator, self.worker_cmd_que)
                self.workerThread = QThread()
                self.workerThread.started.connect(self.worker.run)
                self.worker.signal.connect(self.write_info)
                self.worker.moveToThread(self.workerThread)
                self.workerThread.start()
                self.workerThreadCreated = True
                print("Starting Worker Thread")
                

    @Slot()
    def on_runloop_clicked(self):
        if not self.primaryThreadCreated:
            if not self.workerThreadCreated:
                self.worker_cmd_que = queue.Queue()
                self.worker = WorkerThread(self.serialMarlin, self.generator, self.worker_cmd_que)
                self.workerThread = QThread()
                self.workerThread.started.connect(self.worker.run)
                self.worker.signal.connect(self.write_info)
                self.worker.moveToThread(self.workerThread)
                self.workerThread.start()
                self.workerThreadCreated = True
                print("Starting Worker Thread")

    @Slot()
    def on_btnstoploop_clicked(self):
        pass

    @Slot()
    def on_disconnect_clicked(self):
        if self.marlinPortOpen:
            if self.workerThreadCreated:
                self.worker_cmd_que.put("exit")
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
            if self.bipap_init_threadcreated:
                self.bipapinit.Stop()
                self.bipapinitThread.exit()
                self.bipapinitThread.wait()
                self.bipap_init_threadcreated = False
            self.serialMarlin.close()
            if self.sensorPortOpen:
                self.serialSensor.close()
            self.marlinPortOpen = False
            self.sensorPortOpen = False
            self.connect.setEnabled(True)
            self.disconnect.setEnabled(False)
            self.runloop.setEnabled(False)
            self.btninit.setEnabled(False)

    @Slot()
    def on_btnalarmpage_clicked(self):
        #self.stackedWidget = QStackerWidget()
        self.stackedWidget.setMinimumHeight(110)
        if self.btnalarmpage.isChecked():
            self.stackedWidget.setCurrentIndex(1)
        else:
            self.stackedWidget.setCurrentIndex(0)

    @Slot()
    def on_startpush_clicked(self):
        if not self.bipapthreadcreated:
            self.bipap = BipapThread(self.serialMarlin, self.generator, self.pressureque)
            self.bipapThread = QThread()
            self.bipapThread.started.connect(self.bipap.run)
            #self.bipap.signal.connect(self...)
            self.bipap.moveToThread(self.bipapThread)
            self.bipapThread.start()
            self.bipapthreadcreated = True
            print("Bipap Thread Created")
        self.bipap.StartMoving()
        self.runMode = MachineRunModes.BiPAP

    @Slot()
    def on_connect_clicked(self):
        try:
            self.autoConnect()
        except Exception as ex:
            pprint.pprint(ex)
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
        #self.wave.playstart()
        self.wave.playfile()
        #self.wave.BeepBeep()

    def automatePorts(self):
        self.ports = list(port_list.comports())
        for port in self.ports:
            for itm in port:
                if "USB" in itm:
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

    def autoConnect(self):
        try:
            if not self.marlinPortOpen:
                if self.ComPorts['Marlin'] != 'NA':
                    print("Serial Port Name : " + self.ComPorts['Marlin'])
                    self.serialMarlin = serial.Serial(self.ComPorts['Marlin'], baudrate=115200, timeout=1)
                    time.sleep(1)
                    self.marlinPortOpen = True
                    while self.serialMarlin.in_waiting:
                        self.serialMarlin.readline()
            if self.ComPorts['Sensor'] != 'NA':
                if not self.sensorPortOpen:
                    self.serialSensor = serial.Serial(self.ComPorts['Sensor'], baudrate=115200, timeout=1)
                    self.sensorPortOpen = True
            
        except serial.SerialException as ex:
            self.marlinPortOpen = False
            print(ex.strerror)
            print("Error Opening Serial Port..........................................")
        else:
            self.connect.setEnabled(False)
            self.disconnect.setEnabled(True)
            self.btninit.setEnabled(True)

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
        self.ipaplcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def modeselectionchanged(self):
        if "CMV" in self.modecombobox.currentText():
            self.buttonstack.setCurrentIndex(0)
            self.stackedWidget.setCurrentIndex(0)
        elif "BiPAP" in self.modecombobox.currentText():
            self.buttonstack.setCurrentIndex(2)
            self.stackedWidget.setCurrentIndex(2)

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
        if self.workerThreadCreated:
            self.generator.GenerateBiPAP(self.pparr, self.ipapdial.value())
            self.worker.updateGcode(self.generator)


    def vtDialChanged(self):
        self.vtlcd.display(self.vtdial.value())
        self.vt = self.vtdial.value()
        self.settings_dict[r"vt"] = str(self.vt)
        self.SaveSettings()

    def ieDialChanged(self):
        #self.table.setItem(0,1, QTableWidgetItem(self.settings_dict[r"ie"]))
        self.ielcd.display(self.iedial.value())
        self.ie = self.iedial.value()
        self.settings_dict[r"ie"] = str(self.ie)
        self.SaveSettings()

    def rrDialChanged(self):
        self.rrlcd.display(self.rrdial.value())
        self.rr = self.rrdial.value()
        self.settings_dict[r"rr"] = str(self.rr)
        self.SaveSettings()

    def fioDialChanged(self):
        self.fiolcd.display(self.fiodial.value())
        self.fio2 = self.fiodial.value()
        self.settings_dict[r"fio2"] = str(self.fio2)
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
        self.generator = GcodeGenerator(self.vt, self.rr, self.ie, self.fio2)
        self.generator.GenerateCMV()

    def LungSensorData(self, data_stream):
        #print(data_stream.split(','))
        self.lst = data_stream.split(",")
        self.maxLen = 100  # max number of data points to show on graph
        if(len(self.lst) > 1):
            try:
                if len(self.lungpressuredata) > self.maxLen:
                    self.lungpressuredata.popleft()  # remove oldest
                if len(self.lungpressurepeakdata) > self.maxLen:
                    self.lungpressurepeakdata.popleft()
                if len(self.dvdata) > self.maxLen:
                    self.dvdata.popleft()
                if len(self.kalmandata) > self.maxLen:
                    self.kalmandata.popleft()
                if len(self.voldata) > self.maxLen:
                    self.voldata.popleft()

                self.lungpressurepeakdata.append(float(self.peakdial.value()))
                self.lungpressuredata.append(float(self.lst[1]) + float(self.peepdial.value()))
                self.kalmandata.append(self.kalman.Estimate(float(self.lst[1]) + float(self.peepdial.value())))

                #Logging the data @ 100 data received
                self.log_interval_count += 1
                if self.log_interval_count >= 100:
                    self.log_interval_count = 0
                    self.datalogger.writeBlock(self.lungpressuredata)

                # #In Bipapmode 
                # if self.runMode == MachineRunModes.BiPAP:
                #     #print("Bipap")
                #     try:
                #         #if self.bipapLookup.lookUp(float(self.lst[0]) + float(self.peepdial.value())):
                #         #print(str(float(self.lst[0]) + float(self.peepdial.value())))
                #         if self.ipap < float(float(self.lst[0]) + float(self.peepdial.value())):
                #             print("lookup returns stop....")
                #             if self.bipap.serialmutex.tryLock():
                #                 self.bipap.StopMoving()
                #                 self.bipap.codegen.GenerateBiPAP()
                #                 self.bipap.serl.write(self.bipap.codegen.gcodebipap_back.encode("utf-8"))
                #                 #time.sleep(1)
                #                 #self.bipap.serl.flash
                #                 self.bipap.codegen.bipapstep = 0
                #                 self.bipap.StartMovingAfter(2.7)
                #                 self.bipap.serialmutex.unlock()
                #     except:
                #         print("ERROR bipapLookup")

                if len(self.deriv_points) == 0:
                    self.timesnap = 0.0
                else:
                    self.timesnap = time.perf_counter() - self.tic

                self.deriv_points.append([(float(self.lst[1]) + float(self.peepdial.value())), self.timesnap])
                #self.deriv_points.append([(float(self.kalman.Estimate(float(self.lst[0])))), self.timesnap])
                if len(self.deriv_points) > 3:
                    self.deriv_points.popleft()
                    #self.dvdata.append(((self.deriv_points[2][0] - self.deriv_points[0][0]) / ((self.deriv_points[2][1] - self.deriv_points[0][1]) * 10000)))
                    ###self.dvdata.append(((self.deriv_points[2][0] - self.deriv_points[0][0]) / (0.2)))
                    self.dvdata.append(self.flowprocess.CalculateFlow(float(self.lst[2])))
                    self.sumofvolume += self.flowprocess.CalculateFlow(float(self.lst[2]))
                    self.voldata.append(self.sumofvolume)
                else:
                    self.dvdata.append(0.0)

                if(len(self.deriv_points) >= 3):
                    if self.dvdata[-1] > 1:
                        self.curve1.setPen(self.derivative_pen_in)
                        self.inhale_t_count += 1
                        self.flag_idle = False
                        self.idle_count = 0
                        self.wave.playin()
                    elif self.dvdata[-1] < -1:
                        self.curve1.setPen(self.derivative_pen_out)
                        self.exhale_t_count += 1
                        self.flag_idle = False
                        self.idle_count = 0
                        self.sumofvolume = 0.0
                    else:
                        if not self.flag_idle:
                            self.idle_count += 1
                            if self.idle_count > 2:
                                ###print(f"Inhale {(self.inhale_t_count * 100) / 1000} :: Exhale {(self.exhale_t_count * 100) / 1000}")
                                self.flag_idle = True
                                self.idle_count = 3
                                self.inhale_t_count = 0
                                self.exhale_t_count = 0

                self.tic = time.perf_counter()

                self.curve1.setData(self.lungpressuredata)
                self.curve2.setData(self.lungpressurepeakdata)
                self.curve3.setData(self.kalmandata)
                self.dvcurve.setData(self.dvdata)
                self.volcurve.setData(self.voldata)
            except:
                pass
            else:
                if (float(self.lst[1]) + float(self.peepdial.value())) > self.peakdial.value():
                    if self.sensorThreadCreated:
                        self.wave.playfile()
                        #self.sensor.beep()

    def peepSensorData(self, data_stream):
        #print(data_stream.split(','))
        self.lst = data_stream.split(",")
        self.maxLen = 100  # max number of data points to show on graph
        if(len(self.lst) > 1):
            try:
                if len(self.peeppressuredata) > self.maxLen:
                    self.peeppressuredata.popleft()  # remove oldest
                self.peeppressuredata.append(float(self.lst[1]) + float(self.peepdial.value()))
                self.curve1.setData(self.peeppressuredata)
            except:
                pass
            else:
                if (float(self.lst[1]) + float(self.peepdial.value())) > self.peakdial.value():
                    if self.sensorThreadCreated:
                        self.wave.playfile()

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
        if "Endbipapinit" in data_stream:
            if self.bipap_init_threadcreated:
                self.bipapinitThread.exit()
                self.bipapinitThread.wait()
                self.bipap_init_threadcreated = False
                del self.bipapinitThread
                print("bipapinitThread Closed")

    def endBipap(self, pparr):
        self.pparr = pparr
        pprint.pprint(self.pparr)
        self.btnrunbploop.setEnabled(True)

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
    mw.showFullScreen()
    sys.exit(app.exec_())
