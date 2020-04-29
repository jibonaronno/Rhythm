import sys
import serial
import pprint
import time
import enum
import queue
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt, QMutex

class GcodeStates(enum.Enum):
    WAIT_FOR_TIMEOUT = 1
    GCODE_SENT = 2
    READY_TO_SEND = 3

class BipapInitializationThread(QObject):
    signal = Signal(str)
    #ppsignal = Signal([])

    def __init__(self, serialPort, codegen, que):
        self.pressureque = que
        self.serialPort = serialPort
        self.position_pressure_list = []
        #self.json = JsonSettings("settings.json")
        self.codegen = codegen #GcodeGenerator(int(self.json.dict['vt']), int(self.json.dict['rr']), int(self.json.dict['ie']), int(self.json.dict['fio2']))
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodeinit.splitlines()
        self.flagStop = False
        self.variableDt = self.codegen.Dt
        self.ustr = ""
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

            while self.variableDt < self.codegen.Dp:
                if self.flagStop:
                    break
                try:
                    self.ustr = "G01 X"+str(self.variableDt) + " Y"+str(self.variableDt)+"\r\n"
                    self.serialPort.write((self.ustr.encode("utf-8")))
                    
                    if self.pressureque.qsize() > 0:
                        self.pressureque.get(False)
                    time.sleep(0.12)
                    in_waiting = self.serialPort.in_waiting
                    #while in_waiting == 0:
                        #time.sleep(0.1)
                        #in_waiting = self.serialPort.in_waiting
                        #self.serialPort.reset_input_buffer()
                    if self.pressureque.qsize() > 0:
                        pressure = self.pressureque.get(False)
                        self.position_pressure_list.append([self.variableDt, pressure])
                        self.variableDt += 1

                except serial.SerialException as ex:
                    print("Error In SerialException During Bipap Pushing" + str(ex.strerror))
                    self.signal.emit("Endbipapinit")
                except Exception as e:
                    print("Error In Exception During Bipap Pushing")
                    pprint.pprint(e)
                    self.signal.emit("Endbipapinit")
            
            self.ustr = "G01 X"+str(self.codegen.Dt) + " Y"+str(self.codegen.Dt)+"\r\n"
            self.serialPort.write((self.ustr.encode("utf-8")))
            pprint.pprint(self.position_pressure_list)

            self.signal.emit("Endbipapinit")
        except serial.SerialException as ex:
            print("Error In SerialException" + str(ex.strerror))
            self.signal.emit("Stopped")
        except Exception as e:
            pprint.pprint(e)
            self.signal.emit("Stopped")

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
    def __init__(self, serl, codegen, que):
        self.pressureque = que
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
        self.xyIncr = self.codegen.Dt
        self.gstr = ""
        self.sremsg = ""
        self.serialmutex = QMutex()
        self.startdelay = -1
        super().__init__()

    def gcodestep(self):
        self.gstr = "G01 X" + str(self.xyIncr) + " Y" + str(self.xyIncr) + " F1000\r\n"
        if self.xyIncr < self.codegen.xmax:
            self.xyIncr += 1

    def Stop(self):
        self.flagStop = True

    def updateGcode(self, codegen):
        self.codegen = codegen
        self.codegen.GenerateCMV()
        self.codelist = self.codegen.gcodestr.splitlines()

    def StartMoving(self):
        self.pause = False

    def StartMovingAfter(self, delay):
        self.startdelay = delay

    def StopMoving(self):
        self.pause = True
        self.xyIncr = self.codegen.Dt

    @Slot()
    def run(self):
        lst = []
        while 1:
            if self.flagStop:
                break
            try:
                if not self.pause:
                    if self.gcode_exec_state == GcodeStates.READY_TO_SEND:
                        self.gcodestep()
                        self.serialmutex.lock()
                        self.serl.write(self.gstr.encode("utf-8"))
                        self.serialmutex.unlock()
                        self.gcode_move_count += 1
                        if self.gcode_move_count >= 130:
                            #self.pause = True
                            self.gcode_move_count = 0
                        else:
                            self.gcode_exec_state = GcodeStates.WAIT_FOR_TIMEOUT
                            self.Tic = time.perf_counter()
                    if self.gcode_exec_state == GcodeStates.WAIT_FOR_TIMEOUT:
                        if (time.perf_counter() - self.Tic) >= 0.15:
                            #print("Gcode Executed\r\n")
                            self.gcode_exec_state = GcodeStates.READY_TO_SEND
                elif self.startdelay > 0:
                    time.sleep(self.startdelay)
                    self.startdelay = -1
                    self.pause = False
            except serial.SerialException as ex:
                print("Error In SerialException" + str(ex.strerror))

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
    plst = []
    def __init__(self, serialPort, que):
        self.pressureque = que
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
                self.plst = jMessage.split(",")
                self.signal.emit(jMessage)
                if self.pressureque.qsize() <= 0:
                    self.pressureque.put(self.plst[0])
                if self._beep:
                    self._beep = False
                    self.serialPort.write("A\r\n".encode('utf-8'))
                if self.flag_sensorlimit_tx:
                    self.flag_sensorlimit_tx = False
                    self.serialPort.write(self.strdata.encode('utf-8'))
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)
