# -*- coding: utf-8 -*-

from atsurvey.primitives.distance import *
from atsurvey.primitives.azimuth import *
from typing import Tuple


class Point(object):
    __slots__ = ['name', 'x', 'y', 'z']

    def __init__(self, name: str,
                 x: Union[int, float] = 0.0,
                 y: Union[int, float] = 0.0,
                 z: Union[int, float] = 0.0):
        self.name = name
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self) -> str:
        return f"{self.name:<6}({self.x:<10.3f},{self.y:<11.3f},{self.z:<7.3f})"

    @property
    def cords(self) -> Tuple[Union[int, float]]:
        return tuple([self.x, self.y, self.z])

    def azimuth(self, point, reverse: bool = False) -> Azimuth:
        return Azimuth.from_points(self, point, reverse)

    def distance(self, point) -> EGSADistance:
        return EGSADistance.from_points(self, point)

    def offset(self,
               x: Union[int, float] = 0.0,
               y: Union[int, float] = 0.0,
               z: Union[int, float] = 0.0):
        self.x = self.x + x
        self.y = self.y + y
        self.z = self.z + z

        return self

    def copy(self, name: str = '', z: bool = True):
        _name = self.name if not name else name
        _z = self.z if z else 0.0

        return Point(_name, self.x, self.y, _z)


class Points:
    def __init__(self, x: Any, y: Any, z: Any):
        self.x = self._load(x).round(CORDS_ROUND)
        self.y = self._load(y).round(CORDS_ROUND)
        self.z = self._load(z).round(CORDS_ROUND)

    @staticmethod
    def _load(coordinates: Any) -> np.ndarray:
        return val2array(coordinates)

    @classmethod
    def from_traverse(cls,
                      start: Point,
                      finish: Point,
                      dx: DeltaDistances,
                      dy: DeltaDistances,
                      dz: DeltaDistances):
        _x: list = [start.x]
        _y: list = [start.y]
        _z: list = [start.z]

        for idx, values in enumerate(zip(dx.values, dy.values, dz.values)):
            new_x = _x[idx] + values[0]
            new_y = _y[idx] + values[1]
            new_z = _z[idx] + values[2]
            _x.append(new_x)
            _y.append(new_y)
            _z.append(new_z)

        _x[-2] = finish.x
        _y[-2] = finish.y
        _z[-2] = finish.z

        return cls(_x[:-1], _y[:-1], _z[:-1])


class NonePoint(Point):
    def __init__(self):
        super().__init__("None", 0.0, 0.0, 0.0)
