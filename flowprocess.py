
import math
import sys
from os.path import join, dirname, abspath
import json
import os
from flowsetup import JsonFlowSetup
import pprint
import math

class FlowProcess(object):
    def __initt__(self):
        try:
            config = JsonFlowSetup("flow.json")
            self.D_inlet = config.dict["D_inlet"]
            self.D_orifice = config.dict["D_orifice"]
            self.P_air = config.dict["P_air"]
            self.kcal = config.dict["kcal"]
            self.diameter_ratio = self.D_orifice / self.D_inlet
            self.orifice_area = (math.pi * (self.D_orifice * self.D_orifice)) / 4
            self.inlet_area = (math.pi * (self.D_inlet * self.D_inlet)) / 4
            self.CDD = self.orifice_area / self.inlet_area
            self.Korifice = self.orifice_area * math.sqrt(2/(self.P_air * (1-(self.diameter_ratio ** 4)))) * self.kcal

        except Exception as e:
            pprint.pprint(e)

        self.flow = 0.0        

    def CalculateFlow(self):
        pass