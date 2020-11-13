# -*- coding: utf-8 -*-
from aztool_topo.primitives.angle import *


class Azimuth(Angle):
    def __init__(self, angle):
        super().__init__(angle)

    def __repr__(self):
        return f"Azimuth({self._angleG:.4f})"

    @classmethod
    def from_tuples(cls, a, b, reverse=False):
        dx = b[0] - a[0]
        dy = b[1] - a[1]

        _azimuth = Angle(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.value)

    @classmethod
    def from_points(cls, a, b, reverse=False):
        dx = b.x - a.x
        dy = b.y - a.y

        _azimuth = Angle(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.value)
