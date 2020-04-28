import sys
import serial
import pprint
import time
import enum
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt

class GcodeStates(enum.Enum):
    WAIT_FOR_TIMEOUT = 1
    GCODE_SENT = 2
    READY_TO_SEND = 3

class PrimaryThread(QObject):
    signal = Signal(str)

    def __init__(self, serialPort, codegen):
        self.serialPort = serialPort
        #self.json = JsonSettings("settings.json")
        self.codegen = codegen #GcodeGenerator(int(self.json.dict['vt']), int(self.json.dict['rr']), int(self.json.dict['ie']), int(self.json.dict['fio2']))
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodeprimary.splitlines()
        self.flagStop = False
        super().__init__()

    def Stop(self):
        self.flagStop = True

    @Slot()
    def run(self):
        try:
            lst = []
            for line in self.codelist:
                if self.flagStop:
                    break
                #self.serialPort.reset_input_buffer()
                self.serialPort.write((str(line) + "\r\n").encode("utf-8"))
                time.sleep(0.5)
                in_waiting = self.serialPort.in_waiting
                while in_waiting == 0:
                    time.sleep(1)
                    in_waiting = self.serialPort.in_waiting
                    
                jMessage = ""
                while self.serialPort.in_waiting:
                    #print(self.serialPort.readline().decode('ascii'))
                    lst = self.serialPort.readlines()
                    for itm in lst:
                        jMessage += itm.decode('ascii')
                        #jMessage += self.serialPort.readline().decode('ascii')
                    if "busy" in jMessage:
                        time.sleep(1)
                        continue
                self.signal.emit(str(line) + " - " + jMessage)
            self.signal.emit("StoppedOK")
        except serial.SerialException as ex:
            print("Error In SerialException" + ex.strerror)
            self.signal.emit("Stopped")
        except Exception as e:
            pprint.pprint(e)
            self.signal.emit("Stopped")

class BipapThread(QObject):
    signal = Signal(str)
    def __init__(self, serl, codegen):
        self.serl = serl
        self.codegen = codegen
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodestr.splitlines()
        self.linecount = len(self.codelist)
        self.flagStop = False
        self.pause = True
        self.gcode_exec_state = GcodeStates.READY_TO_SEND
        self.gcode_move_count = 0
        self.presentPosition = (0,0)
        self.Tic = 0
        self.Toc = 0
        super().__init__()

    def Stop(self):
        self.flagStop = True

    def updateGcode(self, codegen):
        self.codegen = codegen
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodestr.splitlines()

    def StartMoving(self):
        self.pause = False

    @Slot()
    def run(self):
        lst = []
        while 1:
            if self.flagStop:
                break
            try:
                if not self.pause:
                    if self.gcode_exec_state == GcodeStates.READY_TO_SEND:
                        #self.serl.write()
                        self.gcode_move_count += 1
                        if self.gcode_move_count >= 30:
                            self.pause = True
                            self.gcode_move_count = 0
                        else:
                            self.gcode_exec_state = GcodeStates.WAIT_FOR_TIMEOUT
                            self.Tic = time.perf_counter()
                    if self.gcode_exec_state == GcodeStates.WAIT_FOR_TIMEOUT:
                        if (time.perf_counter() - self.Tic) >= 1:
                            print("Gcode Executed\r\n")
                            self.gcode_exec_state = GcodeStates.READY_TO_SEND
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)

class WorkerThread(QObject):
    signal = Signal(str)
    def __init__(self, serialPort, codegen):
        self.serialPort = serialPort
        self.codegen = codegen
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodestr.splitlines()
        #pprint.pprint(self.codelist)
        self.linecount = len(self.codelist)
        #for idxx in range(self.linecount):
        #    print(self.codelist[idxx])
        #self.idx = 0
        self.flagStop = False
        super().__init__()

    def Stop(self):
        self.flagStop = True

    def updateGcode(self, codegen):
        self.codegen = codegen
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodestr.splitlines()

    @Slot()
    def run(self):
        lst = []
        while 1:
            if self.flagStop:
                break
            try:
                for line in self.codelist:
                    if self.flagStop:
                        break
                    self.serialPort.write((str(line)+"\r\n").encode('utf-8'))
                    time.sleep(0.1)
                    in_waiting = self.serialPort.in_waiting
                    while in_waiting == 0:
                        time.sleep(1)
                        in_waiting = self.serialPort.in_waiting
                        
                    jMessage = ""
                    while "ok" not in jMessage:
                        while self.serialPort.in_waiting:
                            #print(self.serialPort.readline().decode('ascii'))
                            lst = self.serialPort.readlines()
                            for itm in lst:
                                jMessage += itm.decode('ascii')
                    self.signal.emit(str(line) + " - " + jMessage)
                    #time.sleep(self.codegen.Ti+self.codegen.Th)
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)

class SensorThread(QObject):
    signal = Signal(str)
    def __init__(self, serialPort):
        self.serialPort = serialPort
        self.flagStop = False
        self.jMessage = ""
        self._beep = False
        self.flag_sensorlimit_tx = False
        self.strdata = ""
        super().__init__()

    def Stop(self):
        self.flagStop = True

    def beep(self):
        self._beep = True

    def txsensordata(self, strdata):
        self.strdata = strdata
        self.flag_sensorlimit_tx = True

    @Slot()
    def run(self):
        while 1:
            if self.flagStop:
                break
            try:
                jMessage = self.serialPort.readline().decode('ascii')
                self.signal.emit(jMessage)
                if self._beep:
                    self._beep = False
                    self.serialPort.write("A\r\n".encode('utf-8'))
                if self.flag_sensorlimit_tx:
                    self.flag_sensorlimit_tx = False
                    self.serialPort.write(self.strdata.encode('utf-8'))
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)
