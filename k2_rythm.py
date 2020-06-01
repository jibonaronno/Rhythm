#!/usr/bin/python3
import sys
import enum
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

_UI = join(dirname(abspath(__file__)), 'VentUI.ui')

class AlarmTypes(enum.Enum):
    NO_ALARM = 1
    PEAK_PRESSURE = 2

class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        #startdlg = StartDialog(None)
        
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
        self.volpeakdata = deque()
        self.sumofvolume = 0.0

        self.dvdata = deque()
        self.deriv_points = deque()
        self.timesnap = 0.0
        self.tic = 0.0

        self.lungpressure_line_pen = pg.mkPen(200, 100, 0)
        self.plotter = PlotWidget()
        self.plotter.showGrid(x=True, y=True, alpha=None)
        self.plotter.setTitle("Pressure : mb")
        self.curve1 = self.plotter.plot(0,0,"lungpressure", 'b')
        self.curve2 = self.plotter.plot(0,0,"peakpressure", pen = self.lungpressure_line_pen)
        self.kalmanpen = pg.mkPen(20, 100, 20)
        self.curve3 = self.plotter.plot(0,0, "kalman", pen = self.kalmanpen)

        self.derivative_pen = pg.mkPen(70,90,100, 100)
        self.derivative_pen_in = pg.mkPen(10, 200, 10)
        self.derivative_pen_out = pg.mkPen(10, 200, 200)
        #self.dvcurve = self.plotter.plot(0,0,"dvcurve", pen = self.derivative_pen)

        self.flowpen = pg.mkPen(200, 200, 10)

        self.inhale_t_count = 0
        self.inhale_t = 0
        self.exhale_t = 0
        self.exhale_t_count = 0
        self.flag_idle = True
        self.idle_count = 0

        #self.dvcurve.setPen()

        self.flowplotter = PlotWidget()
        self.flowplotter.showGrid(x=True, y=True, alpha=None)
        self.flowplotter.setTitle("Flow ml/ms")

        self.dvcurve = self.flowplotter.plot(0,0,"dvcurve", pen = self.derivative_pen)
        self.flowcurve = self.flowplotter.plot(0,0,"flowcurve", pen = self.flowpen)
        self.flowpeakcurve = self.flowplotter.plot(0,0,"flowpeakcurve", pen = self.derivative_pen)

        self.flowdata = deque()
        self.flowpeakdata = deque()

        self.volplotter_pen = pg.mkPen(200, 20, 10)
        self.volplotter = PlotWidget()
        self.volplotter.showGrid(x=True, y=True, alpha=None)
        self.volplotter.setTitle("Volume ml")
        self.volcurve = self.volplotter.plot(0,0,"volcurve", self.volplotter_pen)
        self.volpeakcurve = self.volplotter.plot(0,0,"volpeakcurve", self.volplotter_pen)
        
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
        print("D_ratio : " + str(self.flowprocess.diameter_ratio))
        print("orifice area : " + str(self.flowprocess.orifice_area))
        print("inlet area : " + str(self.flowprocess.inlet_area))
        print("Korifice : " + str(self.flowprocess.Korifice))

        #self.bipap = BipapThread("", self.generator)
        self.pressureque = queue.Queue()
        self.bipap_init_threadcreated = False
        self.bipapthreadcreated = False

        self.ipapdial.valueChanged.connect(self.ipapDialChanged)
        self.ipaplcd.display(self.ipapdial.value())
        self.epapdial.valueChanged.connect(self.epapDialChanged)
        self.epaplcd.display(self.epapdial.value())


        self.modecombobox.currentIndexChanged.connect(self.modeselectionchanged)
        self.peepdial.valueChanged.connect(self.peepDialChanged)
        self.peeplcd.display(self.peepdial.value())
        self.peakdial.valueChanged.connect(self.peakDialChanged)
        self.peaklcd.display(self.peakdial.value())
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
        self.btnhault.hide()
        self.portsList.hide()
        self.monitoringPort.hide()
        self.scanPorts.hide()
        self.connect.hide()
        self.disconnect.hide()
        self.btnstream.hide()

        self.kalman = kalman(1.2)

        #self.vtdial.setStyleSheet("{ background-color: rgb(20,20,20) }")

        self.AlarmNumber = AlarmTypes.NO_ALARM

        self.serialMarlin = ""
        self.serialSensor = ""
        self.serialEncoder = ""
        self.ports = list(port_list.comports())

        self.bipapthreadcreated = False

        self.primaryThreadCreated = False
        self.workerThreadCreated = False
        self.sensorThreadCreated = False
        self.encoderThreadCreated = False
        self.marlinPortOpen = False
        self.sensorPortOpen = False
        self.EncoderPortOpen = False
        self.gengcode.hide()
        self.childrenMakeMouseTransparen()

        self.datalogger = DataLogger()
        self.log_interval_count = 0

        self.strtx = "<D,10," + str(self.peepdial.value()) + ".0>\r\n"
        self.flag_sensorlimit_tx = False
        self.sensorLimitTimer = QTimer(self)
        self.sensorLimitTimer.timeout.connect(self.checkSensorLimitChanged)

        self.sensorwatchtimer = QTimer(self)
        self.sensorwatchtimer.timeout.connect(self.reconnectSensor)

        self.lungtimer = QTimer(self)
        self.lungtimer.timeout.connect(self.lungtimeout)

        self.modecombobox.addItem("CMV")
        self.modecombobox.addItem("BiPAP")
        self.modecombobox.addItem("PS")

        self.ComPorts = {'Marlin':'NA', 'Sensor':'NA', 'Encoder':'NA'}
        self.selected_ports = []

        #self.ComPorts['Marlin'] = "COM16"
        #self.ComPorts['Sensor'] = "COM5"
        #self.ComPorts['Marlin'] = "ttyACM0"
        #self.ComPorts['Sensor'] = "ttyACM1"
        
        '''
        self.automatePorts()
        pprint.pprint(self.ComPorts)

        if self.ComPorts['Sensor'] == 'NA':
            self.showdialog("Sensor Controller")

        if self.ComPorts['Marlin'] == 'NA':
            self.showdialog("Motion Controller")
        else:
            self.autoConnect()
        '''

        self.devices = DetectDevices()
        # print("All Ports: ")
        #self.devices.printPorts()
        print("USB Ports: ")
        self.devices.printUsbPorts()
        print("\r\n")
        self.devices.detectCustomBoards()
        print('Marlin Port : ' + self.devices.MarlinPort[0])
        print('Encoder Port : ' + self.devices.EncoderPort[0])
        print('Sensor Port : ' + self.devices.SensorPort[0])

        self.ComPorts['Marlin'] = self.devices.MarlinPort[0]
        self.ComPorts['Encoder'] = self.devices.EncoderPort[0]
        self.ComPorts['Sensor'] = self.devices.SensorPort[0]

        self.autoConnect()
        

        '''
        if self.ComPorts['Marlin'] == 'NA':
            self.showdialog("Motion Controller")
        else:
            self.autoConnect()
        '''

        self.breath_in_tick = False # flag to play the breath in wave file for only once
        self.sensorLimitTimer.start(1000)

        self.enc_elements = []
        self.addEncoderElements()

    def lungtimeout(self):
        self.label_alarm.setText("Alarm: Low Lung Pressure")
        self.wave.playBeep  ()
        self.lungtimer.setInterval(700)
    
    def reconnectSensor(self):
        pass
        '''
        self.sensorwatchtimer.stop()
        if self.sensorThreadCreated:
            self.sensor.Stop()
            self.sensorThread.exit()
            self.sensorThread.wait()
            self.sensorThreadCreated = False
            if self.sensorPortOpen:
                self.serialSensor.close()
                time.sleep(1)
        self.autoConnect()
        self.on_btninit_clicked()
        self.sensorwatchtimer.start(500)
        '''

    enc_focus_index = 0
    def addEncoderElements(self):
        self.enc_elements.append(self.btninit)
        self.enc_elements.append(self.runloop)
        self.enc_elements.append(self.btnstopcmv)
        self.enc_elements.append(self.gcodeshow)
        self.enc_elements.append(self.btnalarmpage)
        self.enc_elements.append(self.btnmachinesetup)
        self.enc_elements.append(self.alarm)
        self.enc_elements.append(self.btnchangeset)

    def encrFocus(self, value=1):
        if value == 1:
            self.enc_focus_index += 1
            print("Focus Index : " + str(self.enc_focus_index))
            pyautogui.press('\t')
            if self.enc_focus_index < len(self.enc_elements):
                self.enc_elements[self.enc_focus_index].setFocus()
        elif value == 0:
            pyautogui.keyDown('shift')
            pyautogui.press('\t')
            pyautogui.keyUp('shift')

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

    def pauseVentilator(self):
        if self.workerThreadCreated:
            self.worker.Stop()

    def resumeVentilator(self):
        if self.workerThreadCreated:
            self.worker.Resume()

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

    left_panel_visible = True

    def show_hide_LeftPanel(self):
        if self.left_panel_visible:
            self.stackedWidget_2.hide()
            self.left_panel_visible = False
        else:
            self.left_panel_visible = True
            self.stackedWidget_2.show()

    def onEncoderValue(self, msg):
        parts = None
        value = 2
        if len(msg) <= 7:
            parts = msg.split(':')
            if len(parts) > 1:
                if parts[0] == '1':
                    value = int(parts[1])
                    if value < 3:
                        self.changeVTdial(value)
                    elif value == 3:
                        if self.workerThreadCreated:
                            if self.worker.flagStop:
                                self.on_runloop_clicked()
                            else:
                                self.on_btnstopcmv_clicked()
                        else:
                            if self.runloop.isEnabled():
                                self.on_runloop_clicked()
                if parts[0] == '2':
                    value = int(parts[1])
                    if value < 3:
                        self.changeIEdial(value)
                    elif value == 3:
                        self.on_btninit_clicked()
                if parts[0] == '3':
                    value = int(parts[1])
                    if value < 3:
                        self.changeRRdial(value)
                    elif value == 3:
                        self.emulateSpace()
                if parts[0] == '4':
                    value = int(parts[1])
                    if value < 3:
                        self.changeFIOdial(value)
                    elif value == 3:
                        self.show_hide_LeftPanel()
                if parts[0] == '5':
                    value = int(parts[1])
                    if value < 3:
                        self.encrFocus(value)
                    elif value == 3:
                        self.change_set(parts[1])

    def emulateEnter(self):
        pyautogui.press('enter')

    def emulateSpace(self):
        pyautogui.press(' ')

    def changeVTdial(self, incr = 1):
        if self.vtdial.isEnabled():
            self.changedial(incr, self.vtdial)

    def changeIEdial(self, incr=1):
        if self.iedial.isEnabled():
            self.changedial(incr, self.iedial)

    def changeRRdial(self, incr=1):
        if self.rrdial.isEnabled():
            self.changedial(incr, self.rrdial)

    def changeFIOdial(self, incr=1):
        if self.fiodial.isEnabled():
            self.changedial(incr, self.fiodial)

    def changedial(self, incr = 1, dial=None):
        if dial != None:
            dial_max = dial.maximum()
            dial_min = dial.minimum()
            dial_now = dial.value()
            if(incr == 1):
                if dial_now >= dial_max:
                    return
                else:
                    dial_now += incr
                    dial.setValue(dial_now)
            elif(incr == 0):
                if dial_now <= dial_min:
                    return
                else:
                    dial_now -= 1
                    dial.setValue(dial_now)


    def getStreamData(self, line):
        elements = line.split('\t')
        if len(elements) > 2:
            print(str(elements[1]))

    flagEditCmv = False

    def changeCmvParams(self):
        self.vtdial.setEnabled(True)
        self.iedial.setEnabled(True)
        self.rrdial.setEnabled(True)
        self.fiodial.setEnabled(True)
        self.btnchangeset.setText("Set")
        self.flagEditCmv = True

    def setCmvParams(self):
        self.vtdial.setEnabled(False)
        self.iedial.setEnabled(False)
        self.rrdial.setEnabled(False)
        self.fiodial.setEnabled(False)
        self.btnchangeset.setText("Change")
        self.flagEditCmv = False

    def change_set(self, cmd):
        print(cmd)
        if '3' in cmd:
            if self.flagEditCmv:
                self.setCmvParams()
            else:
                self.changeCmvParams()

    @Slot()
    def on_peepdisable_clicked(self):
        self.strtx = "<D,1," + str(self.peepdial.value()) + ".0>\r\n"
        self.flag_sensorlimit_tx = True


    @Slot()
    def on_btnchangeset_clicked(self):
        if self.flagEditCmv:
            self.setCmvParams()
        else:
            self.changeCmvParams()

    @Slot()
    def on_btnstream_clicked(self):
        self.streamer = Backfeed('prolog.log')
        self.streamer.setCallback(self.getStreamData)
        self.streamer.Start(50)

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
        if self.marlinPortOpen:
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
                self.sensorwatchtimer.start(500)
                print("Starting Sensor Thread ...")


    def startEncoderThread(self):
        if self.EncoderPortOpen:
            if not self.encoderThreadCreated:
                print('Starting Encoder Thread')
                self.encoder = EncoderThread(self.serialEncoder)
                self.encoderThread = QThread()
                self.encoderThread.started.connect(self.encoder.run)
                self.encoder.signal_pass_encoder.connect(self.on_encoder)
                self.encoder.moveToThread(self.encoderThread)
                self.encoderThread.start()
                self.encoderThreadCreated = True

    def on_encoder(self, data_stream):
        #print(str(data_stream))
        self.onEncoderValue(data_stream)

    
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
                self.lungtimer.start(3000)
                print("Starting Worker Thread")

            elif self.workerThreadCreated:
                self.worker.Resume()
                self.lungtimer.start(3000)

    @Slot()
    def on_btnstopcmv_clicked(self):
        self.pauseVentilator()
        self.lungtimer.stop()

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
        self.devices.detectCustomBoards()
        self.ComPorts['Marlin'] = self.devices.MarlinPort[0]
        self.ComPorts['Encoder'] = self.devices.EncoderPort[0]
        self.ComPorts['Sensor'] = self.devices.SensorPort[0]
        try:
            self.autoConnect()
        except Exception as ex:
            print('Error From on_connect_clicked')
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
        #self.wave.playin()
        #self.wave.playfile()
        self.wave.playBeep()

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

            if self.ComPorts['Encoder'] != 'NA':
                if not self.EncoderPortOpen:
                    self.serialEncoder = serial.Serial(self.ComPorts['Encoder'], baudrate=115200, timeout=0)
                    self.EncoderPortOpen = True
                    self.startEncoderThread()
            
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
        if self.sensorThreadCreated:
            if self.flag_sensorlimit_tx:
                #self.strtx = "<D,10," + str(self.peepdial.value()) + ".0>\r\n" # + "," + str(self.lowpdial.value()) + "," + str(self.peepdial.value()) + "," + str(self.himinitdial.value()) + "," + str(self.lowminitdial.value())
                self.sensor.txsensordata(self.strtx)
                print(self.strtx)
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
        self.labelipap.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.labelepap.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.ipaplcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.epaplcd.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_18.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label_19.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.ilcd_bp.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.elcd_bp.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.rrlcd_bp.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def modeselectionchanged(self):
        if "CMV" in self.modecombobox.currentText():
            self.buttonstack.setCurrentIndex(0)
            self.stackedWidget.setCurrentIndex(0)
            self.label.setText("Mode : CMV")
        elif "BiPAP" in self.modecombobox.currentText():
            self.buttonstack.setCurrentIndex(2)
            self.stackedWidget.setCurrentIndex(2)
        elif "PS" in self.modecombobox.currentText():
            self.label.setText("Mode : PS")

    def peepDialChanged(self):
        self.peeplcd.display(self.peepdial.value())
        self.strtx = "<E,10," + str(self.peepdial.value()) + ".0>\r\n"
        self.flag_sensorlimit_tx = True

    def peakDialChanged(self):
        self.peaklcd.display(self.peakdial.value())
        self.flag_sensorlimit_tx = False

    def lowpDialChanged(self):
        self.lowplcd.display(self.lowpdial.value())
        self.flag_sensorlimit_tx = False

    def himinitDialChanged(self):
        self.himinitlcd.display(self.himinitdial.value())
        self.flag_sensorlimit_tx = False

    def lowminitDialChanged(self):
        self.lowminitlcd.display(self.lowminitdial.value())
        self.flag_sensorlimit_tx = False

    def epapDialChanged(self):
        self.epaplcd.display(self.epapdial.value())

    def ipapDialChanged(self):
        self.ipaplcd.display(self.ipapdial.value())
        self.flag_sensorlimit_tx = False
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

    def parseSensorData(self, data_stream):
        res = [0.0, 0.0, 0.0]
        lst = data_stream.split(',')
        pressure = 0.0
        if len(lst) >= 3:
            try:
                pressure = float(lst[0])
                res[0] = pressure
                pressure = float(lst[1])
                res[1] = pressure
                pressure = float(lst[2])
                res[2] = pressure
            except Exception as e:
                print('Exception Section (Parse Sensor Data):' + str(e))
                return None
        else:
            return None
        return res

    '''Peak detector for Lung Pressure'''
    from signals import SignalDetector
    lung_detector = SignalDetector()

    vol_detector = SignalDetector()

    flow_detector = SignalDetector()

    def processSensorData(self, data_stream):
        pressure_data = self.parseSensorData(data_stream)
        if(pressure_data == None):
            return
        elif len(pressure_data) < 3:
            return

        self.maxLen = 300
        if len(self.lungpressuredata) > self.maxLen:
            self.lungpressuredata.popleft()  # remove oldest
        if len(self.lungpressurepeakdata) > self.maxLen:
            self.lungpressurepeakdata.popleft()
        if len(self.dvdata) > self.maxLen:
            self.dvdata.popleft()
        if len(self.kalmandata) > self.maxLen:
            self.kalmandata.popleft()
        if len(self.volpeakdata) > self.maxLen:
            self.volpeakdata.popleft()
        if len(self.voldata) > self.maxLen:
            self.voldata.popleft()
        if len(self.flowdata) > self.maxLen:
            self.flowdata.popleft()
        
        '''Lung Pressure'''
        self.lungpressurepeakdata.append(float(self.peakdial.value()))
        self.lungpressuredata.append(float(self.lst[0]) + float(self.peepdial.value()))
        
        '''Volume'''
        self.kalmandata.append(self.kalman.Estimate(float(self.lst[0]) * 22))
        
        '''Flow'''
        dflow = self.flowprocess.CalculateFlow(float(self.lst[1]) + 1)
        self.flowdata.append(dflow * 1000)
        self.deriv_points.append([(float(self.lst[0]) + float(self.peepdial.value())), self.timesnap])
        if len(self.deriv_points) > 3:
            self.deriv_points.popleft()
            self.dvdata.append(((self.deriv_points[2][0] - self.deriv_points[0][0]) / (0.2)))
        else:
            self.dvdata.append(0.0)


    def LungSensorData(self, data_stream):
        print(data_stream)
        self.sensorwatchtimer.setInterval(500)
        self.lst = data_stream.split(",")
        self.maxLen = 300  # max number of data points to show on graph
        if(len(self.lst) > 2):
            if len(self.lungpressuredata) > self.maxLen:
                self.lungpressuredata.popleft()  # remove oldest
            if len(self.lungpressurepeakdata) > self.maxLen:
                self.lungpressurepeakdata.popleft()
            if len(self.dvdata) > self.maxLen:
                self.dvdata.popleft()
            if len(self.kalmandata) > self.maxLen:
                self.kalmandata.popleft()
            if len(self.volpeakdata) > self.maxLen:
                self.volpeakdata.popleft()
            if len(self.voldata) > self.maxLen:
                self.voldata.popleft()
            if len(self.flowdata) > self.maxLen:
                self.flowdata.popleft()
            if len(self.flowpeakdata) > self.maxLen:
                self.flowpeakdata.popleft()

            try:
                self.lungpressurepeakdata.append(float(self.peakdial.value()))
                self.lungpressuredata.append(float(self.lst[0]) + float(self.peepdial.value()))
                self.lung_detector.Cycle(float(self.lst[0]))
                self.peak_lung.setText('Lung Peak: ' + str(self.lung_detector.peak_value) + 'mb')
                if self.lung_detector.peak_value > 5:
                    self.lungtimer.setInterval(3000)
                ''' Commented for testing '''

                '''Volume data came from kalman of lungpressure'''
                ###self.kalmandata.append(self.kalman.Estimate(float(self.lst[0]) + float(self.peepdial.value())))
                self.kalmandata.append(self.kalman.Estimate(float(self.lst[0]) * 22))
                self.voldata.append(self.kalman.Estimate(float(self.lst[0]) * 22))
                self.vol_detector.Cycle(self.kalman.Estimate(float(self.lst[0]) * 22))
                self.volpeakdata.append(500.0)
                self.peak_vol.setText("Vol Peak: " + str(self.vol_detector.peak_value) + 'ml')

                dflow = self.flowprocess.CalculateFlow(float(self.lst[1]) + 1)
                self.flowdata.append(dflow * 1000)
                self.flow_detector.Cycle(dflow * 1000)
                self.peak_flow.setText("Flow Peak: " + str(self.flow_detector.peak_value) + 'ml/ms')
                self.flowpeakdata.append(2)
            except Exception as e:
                print("Exception in LungSensorData(...) : " + str(e))

            #Logging the data @ 100 data received
            '''
            self.log_interval_count += 1
            if self.log_interval_count >= 100:
                self.log_interval_count = 0
                self.datalogger.writeBlock(self.lungpressuredata)
            '''

            if len(self.deriv_points) == 0:
                self.timesnap = 0.0
            else:
                self.timesnap = time.perf_counter() - self.tic

            try:
                self.deriv_points.append([(float(self.lst[0]) + float(self.peepdial.value())), self.timesnap])
                #self.deriv_points.append([(float(self.kalman.Estimate(float(self.lst[0])))), self.timesnap])
                if len(self.deriv_points) > 3:
                    self.deriv_points.popleft()
                    '''
                    cannot remember its effect. seems not feasible output in case of peak detection could be delayed a bit.
                    self.dvdata.append(((self.deriv_points[2][0] - self.deriv_points[0][0]) / ((self.deriv_points[2][1] - self.deriv_points[0][1]) * 10000)))
                    '''
                    '''
                    Working code for derivative data from lung pressure data.
                    '''
                    self.dvdata.append(((self.deriv_points[2][0] - self.deriv_points[0][0]) / (0.2)))

                    '''
                    Following instruction will derive the data from the kalman of lung pressure.
                    '''
                    ''' Working code commented to see speed '''
                    #self.dvdata.append(((self.kalmandata[2] - self.kalmandata[0]) / (0.2)))

                    #self.dvdata.append(float(self.lst[1]))
                    
                    #self.dvdata.append(self.flowprocess.CalculateFlow(float(self.lst[1])))
                    #print("Flow -- " + str(dflow * 1000000))
                    #self.dvdata.append(dflow * 1000000)

                    ''' Working Code commented to check speed '''
                    
                    #self.voldata.append(self.flowprocess.sum_of_volume)
                    #self.dvdata.append(dflow)
                    #self.sumofvolume += self.flowprocess.CalculateFlow(float(self.lst[2]))
                    #self.voldata.append(self.sumofvolume)
                else:
                    self.dvdata.append(0.0)
            except Exception as e:
                print("Exception Section 0x05" + str(e))

            try:
                if(len(self.deriv_points) >= 3):
                    if self.dvdata[-1] > 1:
                        self.curve1.setPen(self.derivative_pen_in)
                        self.inhale_t_count += 1
                        self.flag_idle = False
                        self.idle_count = 0
                        if not self.breath_in_tick:
                            self.breath_in_tick = True
                            self.wave.playin()
                    elif self.dvdata[-1] < -1:
                        self.curve1.setPen(self.derivative_pen_out)
                        self.exhale_t_count += 1
                        self.flag_idle = False
                        self.idle_count = 0
                        self.sumofvolume = 0.0
                        if self.breath_in_tick:
                            self.breath_in_tick = False
                            '''Reset the over pressure alarm when next peak is detcted'''
                            if self.lung_detector.peak_value > 5:
                                self.label_alarm.setText("Alarm: ")
                    else:
                        if not self.flag_idle:
                            self.idle_count += 1
                            if self.idle_count > 2:
                                ###print(f"Inhale {(self.inhale_t_count * 100) / 1000} :: Exhale {(self.exhale_t_count * 100) / 1000}")
                                self.flag_idle = True
                                self.idle_count = 3
                                self.inhale_t_count = 0
                                self.exhale_t_count = 0
            except Exception as e:
                print("Exception Section:0X02 : " + str(e))

            self.tic = time.perf_counter()

            self.curve1.setData(self.lungpressuredata)
            self.curve2.setData(self.lungpressurepeakdata)
            #self.curve3.setData(self.kalmandata)
            
            '''Assign volume data to volume plotter curve'''
            #(originally kalman data) self.volcurve.setData(self.kalmandata)
            self.volcurve.setData(self.voldata)
            self.volpeakcurve.setData(self.volpeakdata)

            '''Assign Flowdata to flow plotter curve & dvdata to dvcurve'''
            self.flowcurve.setData(self.flowdata)
            self.dvcurve.setData(self.dvdata)
            self.flowpeakcurve.setData(self.flowpeakdata)
            
            try:
                if (float(self.lst[0]) + float(self.peepdial.value())) > float(self.peakdial.value()):
                    if self.sensorThreadCreated:
                        self.wave.playfile()
                        self.label_alarm.setText("Alarm: Over Pressure")
                
                        #self.sensor.beep()
            except Exception as e:
                print("Exception section 0x06 : " + str(e))

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
