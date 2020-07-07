
import sys
import enum
from os.path import join, dirname, abspath
import math
import os
import numpy as np
import random
import qtmodern.styles
import qtmodern.windows
import time
import json
import pprint
import queue

class JsonObject(object):
    def __init__(self , location):
        self.location = os.path.expandvars(location)
        self.load(self.location)
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