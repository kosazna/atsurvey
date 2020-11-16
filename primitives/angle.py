# -*- coding: utf-8 -*-
from aztool_topo.util import *


class Angle:
    def __init__(self, angle):
        self._angleG = resolve_angle(angle)
        self._angleR = grad2rad(self._angleG)

    def __repr__(self):
        return f"Angle({self._angleG:.4f})"

    def __len__(self):
        return 1

    def __add__(self, other):
        if isinstance(other, Angle):
            _val = self.value + other.value
        elif isinstance(other, (float, int)):
            _val = self.value + other
        else:
            raise TypeError(f"Unsupported addition type: {type(other)}")

        return Angle(_val)

    def __sub__(self, other):
        if isinstance(other, Angle):
            _val = self.value - other.value
        elif isinstance(other, (float, int)):
            _val = self.value - other
        else:
            raise TypeError(f"Unsupported subtraction type: {type(other)}")

        return Angle(_val)

    @property
    def value(self):
        return self._angleG

    @property
    def rad(self):
        return self._angleR

    @property
    def grad(self):
        return self._angleG

    @property
    def cos(self):
        return np.cos(self._angleR)

    @property
    def sin(self):
        return np.sin(self._angleR)

    def sum(self):
        return self._angleG

    @property
    def reverse(self):
        return round(400 - self._angleG, ANGLE_ROUND)


class Angles:
    def __init__(self, angles):
        self._anglesG: np.ndarray = resolve_angle(self._load(angles))
        self._anglesR: np.ndarray = grad2rad(self._anglesG)

    def __repr__(self):
        return f"Angles({self._anglesG.round(4)})"

    def __len__(self):
        return len(self._anglesG)

    def __contains__(self, item):
        if isinstance(item, float):
            return item in self._anglesG
        elif isinstance(item, Angle):
            return item.value in self._anglesG

    def __add__(self, other):
        if isinstance(other, Angles):
            _val = self.values + other.values
        elif isinstance(other, (int, float, np.ndarray)):
            _val = self.values + other
        else:
            raise TypeError(f"Unsupported addition type: {type(other)}")

        return Angles(_val)

    @staticmethod
    def _load(angles):
        return val2array(angles, Angles)

    @property
    def values(self):
        return self._anglesG

    @property
    def rad(self):
        return self._anglesR

    @property
    def grad(self):
        return self._anglesG

    @property
    def cos(self):
        return np.cos(self._anglesR)

    @property
    def sin(self):
        return np.sin(self._anglesR)

    def sum(self):
        return round(np.nansum(self._anglesG), ANGLE_ROUND)

    @property
    def reverse(self):
        return (400 - self._anglesG).round(ANGLE_ROUND)

    def resolve(self):
        over_400 = np.where(self._anglesG > 400, self._anglesG % 400,
                            self._anglesG)
        under_0 = np.where(over_400 < 0, over_400 + abs(over_400 // 400) * 400,
                           over_400)

        self._anglesG = under_0.round(ANGLE_ROUND)

        return self
