# -*- coding: utf-8 -*-
from aztool_topo.core.computation import *


class Distance:
    def __init__(self, distance, kind='S'):
        self._init_type = kind.upper()
        self._slope = 0.0
        self._horizontal = 0.0
        self._reference = 0.0
        self._egsa = 0.0
        self._dh = 0.0
        self._init_data(distance)

    def _init_data(self, distance):
        if self._init_type == 'S':
            self.slope = distance
        elif self._init_type == 'H':
            self._horizontal = distance
        elif self._init_type == 'R':
            self._reference = distance
        elif self._init_type == 'E':
            self._egsa = distance
        elif self._init_type == 'DH':
            self._dh = distance
        else:
            raise TypeError(f"Valid init kind: [S, H, R, E, DH]")

    def calc_horizontal(self, vangle):
        return round(self._slope * vangle.sin, DIST_ROUND)

    def calc_reference(self, elevation):
        return round(self._horizontal * (EARTH_C / (EARTH_C + elevation)),
                     DIST_ROUND)

    def calc_egsa(self, k):
        return round(self._reference * k, DIST_ROUND)

    def calc_dh(self, vangle, sh, th):
        return round(self._slope * vangle.cos + sh - th, DIST_ROUND)

    def adjust(self):
        pass
