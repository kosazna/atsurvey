# -*- coding: utf-8 -*-
from aztool_topo.util.misc import *
from aztool_topo.core.computation import grad2rad


def resolve(angle):
    if 0 <= angle <= 400:
        return angle
    elif angle > 400:
        return round(angle % 400, ANGLE_ROUND)
    else:
        return round(angle + abs(angle // 400) * 400, ANGLE_ROUND)


class Angle:
    def __init__(self, angle):
        self._angleG = resolve(angle)
        self._angleR = grad2rad(self._angleG)

    def __repr__(self):
        return f"Angle({self._angleG})"

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

    @staticmethod
    def round(angle):
        return round(angle, ANGLE_ROUND)

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

    @property
    def count(self):
        return 1

    @property
    def sum(self):
        return self._angleG

    @property
    def reverse(self):
        return self.round(400 - self._angleG)


class Angles(Angle):
    def __init__(self, angles):
        super().__init__(angles)
        self._anglesG: np.ndarray = self._load(self._angleG)
        self._anglesR: np.ndarray = self._load(self._angleR)

    @staticmethod
    def _load(angles):
        if isinstance(angles, pd.Series):
            return angles.values
        elif isinstance(angles, pd.Series):
            return angles
        elif isinstance(angles, list):
            return np.array(angles)
        else:
            raise TypeError(f"Unsupported init type: {type(angles)}")

    def __contains__(self, item):
        if isinstance(item, float):
            return item in self._anglesG
        elif isinstance(item, Angle):
            return item.value in self._anglesG

    @property
    def values(self):
        return self._anglesG

    @property
    def count(self):
        return len(self._anglesG)

    @property
    def sum(self):
        return self._anglesG.sum()

    @property
    def reverse(self):
        return (400 - self._anglesG).round(ANGLE_ROUND)

    def resolve(self):
        over_400 = np.where(self._anglesG > 400, self._angleG % 400,
                            self._angleG)
        under_0 = np.where(over_400 < 0, over_400 + abs(over_400 // 400) * 400,
                           over_400)

        self._anglesG = under_0.round(ANGLE_ROUND)

        return self
