import math
import sys
from os.path import join, dirname, abspath
from machinesetup import MachineSetup

class GcodeGenerator(object):
    def __init__(self, vt, rr, ie, fio2):
        self.vt = vt
        self.rr = rr
        self.ie = ie
        self.fio2 = fio2
        self.ACC=1000
        self.xmax = 75 #60
        self.xamb = 40 #12
        self.xrect = 30
        self.xcon_offset = 5
        self.vtmax = 5000

        self.machinesetup = MachineSetup()
        self.ACC = self.machinesetup.ACC
        self.xmax = self.machinesetup.xmax
        self.xamb = self.machinesetup.xamb
        self.xrect = self.machinesetup.xrect
        self.xcon_offset = self.machinesetup.xcon_offset
        self.vtmax = self.machinesetup.vtmax
        print(str(self.ACC) + "," + str(self.xmax) + "," + str(self.xamb) + "," + str(self.xrect) + "," + str(self.xcon_offset) + "," + str(self.vtmax))

    def ComputeBipap(self):
        self.xcon = self.xamb + self.xcon_offset
        self.Dt = self.xmax - self.xrect
        self.xav = self.xrect * (self.vt / self.vtmax)
        self.Dp = self.Dt + self.xav
        self.TDMS = 0        
    
    def ComputeCMV(self):
        self.Dt = self.xmax - self.xrect
        self.xav = self.xrect * (self.vt / self.vtmax)
        self.Dp = self.Dt + self.xav
        self.TDMS = 0

        self.Kie =  1/self.ie
        self.BCT = 60*(1-0.24) / self.rr
        self.Ti = self.BCT / (1 + (1 / self.Kie))
        self.Th = self.BCT - self.Ti
        
        self.midpart_ti=(1-self.ACC*self.Ti*self.Ti)/2
        self.lastpart_ti=self.xav*self.xav/4
        self.identifier_ti=math.sqrt(self.midpart_ti*self.midpart_ti-4*self.lastpart_ti)
        self.sol1_ti=(-1*self.midpart_ti+self.identifier_ti)/2
        self.sol2_ti=(-1*self.midpart_ti-self.identifier_ti)/2

        if self.sol1_ti>self.xav:
            if self.sol2_ti>self.xav:
                self.dsmall_ti=0.1
            else:
                self.dsmall_ti=self.sol2_ti
        else:
            self.dsmall_ti=self.sol1_ti  
               
        #print(self.identifier_ti)
        self.midpart_th=(1-self.ACC*self.Th*self.Th)/2
        self.lastpart_th=self.xav*self.xav/4
        self.identifier_th=math.sqrt(self.midpart_th*self.midpart_th-4*self.lastpart_th)
        self.sol1_th=(-1*self.midpart_th+self.identifier_th)/2
        self.sol2_th=(-1*self.midpart_th-self.identifier_th)/2

        if self.sol1_th>self.xav:
            if self.sol2_th>self.xav:
                self.dsmall_th=0.1
            else:
                self.dsmall_th=self.sol2_th
        else:
            self.dsmall_th=self.sol1_th 

     
        #self.ACC_inhale = (4 * self.xav) / (self.Ti * self.Ti)
        #self.ACC_exhale = (4 * self.xav) / (self.Th * self.Th)
        
       # self.Vi = self.ACC_inhale * (self.Ti / 2) * 60
       #self.Vh = self.ACC_exhale * (self.Th / 2) * 60
        self.vimax=math.sqrt(2*self.dsmall_ti*self.ACC)
        self.vhmax=math.sqrt(2*self.dsmall_th*self.ACC)
        self.ViAvg = self.vimax * 60
        #print(self.ViAvg)

        self.Vi = self.ViAvg
        
        self.VhAvg = self.vhmax* 60
        self.Vh = self.VhAvg
        
    def GenerateCMV(self):
        self.ComputeCMV()
        self.gcodeprimary = "G21\r\nG80\r\nG90\r\nG28 X0Y0 F500\r\nM92 X800 Y800\r\nM201 X"+str(self.ACC)+" Y"+str(self.ACC)+"\r\nG01 X" + str(int(self.Dp)) + " Y" + str(int(self.Dp)) + " F500\r\n" + "G01 X" + str(int(self.Dt))+" Y"+str(int(self.Dt))+" F500\r\n"
        self.gcodestr =  "G01 X" + str(int(self.Dp))+" Y"+str(int(self.Dp))+" F"+str(int(self.ViAvg))+"\r\n" +"G01 X"+str(int(self.Dt))+" Y"+str(int(self.Dt))+" F"+str(int(self.VhAvg))+"\r\n" #+"G04 P"+str(self.TDMS)+"\r\n"
       # self.gcodestr = "M201 X" + str(int(self.ACC_inhale)) + " Y" + str(int(self.ACC_exhale)) + "\r\n" + " G01 X" + str(int(self.Dp))+" Y"+str(int(self.Dp))+" F"+str(int(self.Vi))+"\r\n"+ "M201 X"+ str(int(self.ACC_exhale)) + " Y"+ str(int(self.ACC_exhale)) + "\r\n" +" G01 X"+str(int(self.Dt))+" Y"+str(int(self.Dt))+" F"+str(int(self.Vh))+"\r\n" #+"G04 P"+str(self.TDMS)+"\r\n"
        with open('primary.gcode', 'w') as writer:
            writer.write(self.gcodeprimary)
