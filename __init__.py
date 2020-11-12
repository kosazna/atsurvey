# -*- coding: utf-8 -*-
import warnings
from core.project import *

warnings.filterwarnings("ignore")

pd.set_option('display.max_colwidth', -1)
pd.set_option('display.float_format', lambda x: '%.4f' % x)
