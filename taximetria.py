# -*- coding: utf-8 -*-
from .data import *


class Sideshot(object):
    __slots__ = ['tm', 'bs', 'station', 'a', 'mean_elevation', 'k', 'points']

    def __init__(self,
                 data: pd.DataFrame,
                 station: Point = None,
                 bs: Point = None):
        self.tm = data.copy()

        self.bs = bs
        self.station = station
        self.a = station.azimuth(bs)
        self.mean_elevation = round((self.station.z + self.bs.z) / 2, 3)
        self.k = calc_k(station.x, bs.x)

        self.points = Container()

    def compute(self):
        self.tm['h_dist'] = slope_to_hor(self.tm['slope_dist'],
                                         self.tm['v_angle'])

        self.tm['surf_dist'] = surface_distance(self.tm['h_dist'],
                                                self.mean_elevation)

        self.tm['egsa_dist'] = egsa_distance(self.tm['surf_dist'],
                                             self.k)

        self.tm['azimuth'] = azimuth_from_measurement(self.a,
                                                      self.tm['h_angle'])

        self.tm['X'] = calc_X(self.station.x,
                              self.tm['egsa_dist'],
                              self.tm['azimuth'])

        self.tm['Y'] = calc_Y(self.station.y,
                              self.tm['egsa_dist'],
                              self.tm['azimuth'])

        self.tm['Z'] = calc_Z(self.station.z,
                              self.tm['slope_dist'],
                              self.tm['v_angle'],
                              self.tm['station_h'],
                              self.tm['target_h'])

        self.tm['station'] = self.tm['fs']

        self.points = Container(self.tm[['station', 'X', 'Y', 'Z']])

    def to_shp(self, dst: (str, Path), name: str, round_z=2):
        self.points.to_shp(dst=dst, name=name, round_z=round_z)

    def to_excel(self, dst: (str, Path), name: str, decimals=4):
        self.points.to_excel(dst=dst, name=name, decimals=decimals)

    def to_csv(self, dst: (str, Path), name: str, decimals=4, point_id=False):
        self.points.to_csv(dst=dst, name=name, decimals=decimals,
                           point_id=point_id)
