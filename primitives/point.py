# -*- coding: utf-8 -*-
import numpy as np


class Point(object):
    __slots__ = ['name', 'x', 'y', 'z']

    def __init__(self, name: str,
                 x: float = 0.0,
                 y: float = 0.0,
                 z: float = 0.0):

        self.name = name
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self) -> str:
        return f"{self.name:<6}({self.x:<10.3f},{self.y:<11.3f},{self.z:<7.3f})"

    @property
    def cords(self):
        return tuple([self.x, self.y, self.z])

    def split(self):
        return tuple([self.name, self.cords])

    def azimuth(self, point, reverse: bool = False) -> float:
        dx = point.x - self.x
        dy = point.y - self.y

        delta = round(np.arctan(abs(dx) / abs(dy)), 8)
        delta_grad = round((delta * 200) / np.pi, 8)

        if dx > 0 and dy > 0:
            return delta_grad if not reverse else 400 - delta_grad
        elif dx > 0 and dy < 0:
            return 200 - delta_grad if not reverse else 200 + delta_grad
        elif dx < 0 and dy < 0:
            return 200 + delta_grad if not reverse else 200 - delta_grad
        elif dx < 0 and dy > 0:
            return 400 - delta_grad if not reverse else delta_grad

    def distance(self, point) -> float:
        dx = point.x - self.x
        dy = point.y - self.y

        return round(np.sqrt(dx ** 2 + dy ** 2), 8)

    def offset(self, x=0.0, y=0.0, z=0.0):
        self.x = self.x + x
        self.y = self.y + y
        self.z = self.z + z

        return self

    def copy(self, name='', z=True):
        _name = self.name if not name else name
        _z = self.z if z else 0.0

        return Point(_name, self.x, self.y, _z)
