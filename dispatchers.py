import sys
import serial
import pprint
from os.path import join, dirname, abspath
from qtpy.QtCore import Slot, QTimer, QThread, Signal, QObject, Qt

class PrimaryThread(QObject):
    signal = Signal(str)

    def __init__(self, s, codegen):
        self.s = s
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
                #self.s.reset_input_buffer()
                self.s.write((str(line) + "\r\n").encode("utf-8"))
                time.sleep(0.5)
                in_waiting = self.s.in_waiting
                while in_waiting == 0:
                    time.sleep(1)
                    in_waiting = self.s.in_waiting
                    
                jMessage = ""
                while self.s.in_waiting:
                    #print(self.s.readline().decode('ascii'))
                    lst = self.s.readlines()
                    for itm in lst:
                        jMessage += itm.decode('ascii')
                        #jMessage += self.s.readline().decode('ascii')
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


class WorkerThread(QObject):
    signal = Signal(str)

    def __init__(self, s, codegen):
        self.s = s
        self.json = JsonSettings("settings.json")
        self.codegen = codegen #GcodeGenerator(int(self.json.dict['vt']), int(self.json.dict['rr']), int(self.json.dict['ie']), int(self.json.dict['fio2']))
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
                    self.s.write((str(line)+"\r\n").encode('utf-8'))
                    time.sleep(0.1)
                    in_waiting = self.s.in_waiting
                    while in_waiting == 0:
                        time.sleep(1)
                        in_waiting = self.s.in_waiting
                        
                    jMessage = ""
                    while "ok" not in jMessage:
                        while self.s.in_waiting:
                            #print(self.s.readline().decode('ascii'))
                            lst = self.s.readlines()
                            for itm in lst:
                                jMessage += itm.decode('ascii')
                    self.signal.emit(str(line) + " - " + jMessage)
                    #time.sleep(self.codegen.Ti+self.codegen.Th)
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)

            # doFunc(self.signal, jMessage)

class SensorThread(QObject):
    signal = Signal(str)
    def __init__(self, s):
        self.s = s
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
                jMessage = self.s.readline().decode('ascii')
                self.signal.emit(jMessage)
                if self._beep:
                    self._beep = False
                    self.s.write("A\r\n".encode('utf-8'))
                if self.flag_sensorlimit_tx:
                    self.flag_sensorlimit_tx = False
                    self.s.write(self.strdata.encode('utf-8'))
            except serial.SerialException as ex:
                print("Error In SerialException" + ex.strerror)
