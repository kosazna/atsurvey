# -*- coding: utf-8 -*-
from aztool_topo.util import *


class Angle:
    def __init__(self, angle):
        self._angleG = resolve_angle(angle)
        self._angleR = grad2rad(self._angleG)

    def __repr__(self):
        return f"Angle({self._angleG:.4f})"

    def __str__(self):
        return f"{self._angleG:.4f}"

    def __format__(self, format_spec):
        return self._angleG.__format__(format_spec)

    def __bool__(self):
        return bool(self._angleG)

    def __len__(self):
        return 1

    def __float__(self):
        return float(self.value)

    def __add__(self, other):
        _val = self.value + instance2val(other)

        return Angle(_val)

    def __radd__(self, other):
        return self.__add__(instance2val(other))

    def __iadd__(self, other):
        return self.__add__(instance2val(other))

    def __sub__(self, other):
        _val = self.value - instance2val(other)

        return Angle(_val)

    def __rsub__(self, other):
        _val = self.value - instance2val(other)

        return Angle(_val)

    def __isub__(self, other):
        return self.__sub__(instance2val(other))

    def __mul__(self, other):
        _val = self.value * instance2val(other)

        return _val

    def __rmul__(self, other):
        _val = self.value * instance2val(other)

        return _val

    def __eq__(self, other):
        _bool = self.value == instance2val(other)

        return _bool

    def __ne__(self, other):
        _bool = self.value != instance2val(other)

        return _bool

    def __gt__(self, other):
        _bool = self.value > instance2val(other)

        return _bool

    def __lt__(self, other):
        _bool = self.value < instance2val(other)

        return _bool

    def __ge__(self, other):
        _bool = self.value >= instance2val(other)

        return _bool

    def __le__(self, other):
        _bool = self.value <= instance2val(other)

        return _bool

    @property
    def value(self) -> Union[float, int]:
        return self._angleG

    @property
    def rad(self) -> Union[float, int]:
        return self._angleR

    @property
    def grad(self) -> Union[float, int]:
        return self._angleG

    @property
    def cos(self) -> Union[float, int]:
        return round(np.cos(self._angleR), ANGLE_ROUND)

    @property
    def sin(self) -> Union[float, int]:
        return round(np.sin(self._angleR), ANGLE_ROUND)

    @property
    def reverse(self) -> Union[float, int]:
        return round(400 - self._angleG, ANGLE_ROUND)

    def sum(self) -> Union[float, int]:
        return self._angleG


class Angles:
    def __init__(self, angles):
        self._anglesG: np.ndarray = resolve_angle(self._load(angles))
        self._anglesR: np.ndarray = grad2rad(self._anglesG)

    def __repr__(self):
        return f"Angles({self._anglesG.round(4)})"

    def __str__(self):
        return f"{self._anglesG.round(4)}"

    def __len__(self):
        return len(self._anglesG)

    def __iter__(self):
        return iter(self._anglesG)

    def __contains__(self, item):
        if isinstance(item, (int, float)):
            return item in self._anglesG
        elif isinstance(item, Angle):
            return item.value in self._anglesG
        elif isinstance(item, (list, tuple, np.ndarray, pd.Series, Angles)):
            return all([i in self._anglesG for i in item])

    def __add__(self, other):
        _val = self.values + val2array(other)

        return Angles(_val)

    def __radd__(self, other):
        if other == 0:
            return self
        else:
            return self.__add__(other)

    def __sub__(self, other):
        _val = self.values - val2array(other)

        return Angles(_val)

    def __rsub__(self, other):
        if other == 0:
            return self
        else:
            return self.__sub__(other)

    def __getitem__(self, item):
        try:
            return self._anglesG[item]
        except IndexError:
            print(f"  -IndexError- Last index: {len(self) - 1}")

    def __setitem__(self, key, value):
        try:
            self._anglesG[key] = value
            self._anglesR = grad2rad(self._anglesG)
        except IndexError:
            print(f"  -IndexError- Last index: {len(self) - 1}")

    @staticmethod
    def _load(angles):
        return val2array(angles)

    @property
    def values(self) -> np.ndarray:
        return self._anglesG

    @property
    def rad(self) -> np.ndarray:
        return self._anglesR

    @property
    def grad(self) -> np.ndarray:
        return self._anglesG

    @property
    def cos(self) -> np.ndarray:
        return np.cos(self._anglesR).round(ANGLE_ROUND)

    @property
    def sin(self) -> np.ndarray:
        return np.sin(self._anglesR).round(ANGLE_ROUND)

    def sum(self) -> Union[float, int]:
        return round(np.nansum(self._anglesG), ANGLE_ROUND)

    @property
    def reverse(self) -> np.ndarray:
        return (400 - self._anglesG).round(ANGLE_ROUND)
