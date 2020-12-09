# -*- coding: utf-8 -*-
from atsurvey.primitives.angle import *


class Distance:
    def __init__(self, distance):
        self._distance = distance

    def __repr__(self):
        return f"Distance({self._distance:.4f})"

    def __str__(self):
        return f"{self._distance:.4f}"

    def __format__(self, format_spec):
        return self._distance.__format__(format_spec)

    def __bool__(self):
        return bool(self._distance)

    def __len__(self):
        return 1

    def __float__(self):
        return float(self.value)

    def __add__(self, other):
        _val = self.value + instance2val(other)

        return Distance(_val)

    def __radd__(self, other):
        return self.__add__(instance2val(other))

    def __iadd__(self, other):
        return self.__add__(instance2val(other))

    def __sub__(self, other):
        _val = self.value - instance2val(other)

        return Distance(_val)

    def __rsub__(self, other):
        return self.__sub__(instance2val(other))

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
        return self._distance

    def sum(self) -> Union[float, int]:
        return self.value


class SlopeDistance(Distance):
    def __init__(self, distance):
        super().__init__(distance)

    def __repr__(self):
        return f"SlopeDistance({self._distance:.4f})"

    @vectorize
    def to_horizontal(self, vangles):
        _horizontal = slope2hor(self._distance, vangles.values)

        return HorizontalDistance(_horizontal)

    @vectorize
    def to_delta(self, vangle: Angle, sh, th):
        _delta = p2p_dh(self._distance,
                        vangle.value,
                        sh,
                        th)

        return DeltaDistance(_delta)


class HorizontalDistance(Distance):
    def __init__(self, distance):
        super().__init__(distance)

    def __repr__(self):
        return f"HorizontalDistance({self._distance:.4f})"

    @vectorize
    def to_reference(self, elevation):
        _reference = hor2ref(self._distance, elevation)

        return ReferenceDistance(_reference)


class ReferenceDistance(Distance):
    def __init__(self, distance):
        super().__init__(distance)

    def __repr__(self):
        return f"ReferenceDistance({self._distance:.4f})"

    @vectorize
    def to_egsa(self, k):
        _egsa = ref2egsa(self._distance, k)

        return EGSADistance(_egsa)


class EGSADistance(Distance):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"EGSADistance({self._distance:.4f})"

    @classmethod
    def from_points(cls, a, b):
        dx = b.x - a.x
        dy = b.y - a.y

        return round(np.sqrt(dx ** 2 + dy ** 2), DIST_ROUND)


class DeltaDistance(Distance):
    def __init__(self, distance):
        super().__init__(distance)

    def __repr__(self):
        return f"DeltaDistance({self._distance:.4f})"


class Distances:
    def __init__(self, distances):
        self._distances = self._load(distances)

    def __repr__(self):
        return f"Distances({self._distances.round(4)})"

    def __str__(self):
        return f"{self._distances.round(4)}"

    def __len__(self):
        return len(self._distances)

    def __iter__(self):
        return iter(self._distances)

    def __contains__(self, item):
        if isinstance(item, (int, float)):
            return item in self._distances
        elif isinstance(item, Angle):
            return item.value in self._distances
        elif isinstance(item, (list, tuple, np.ndarray, pd.Series, Angles)):
            return all([i in self._distances for i in item])

    def __add__(self, other):
        _val = self.values + val2array(other)

        return Distances(_val)

    def __radd__(self, other):
        if other == 0:
            return self
        else:
            return self.__add__(other)

    def __sub__(self, other):
        _val = self.values - val2array(other)

        return Distances(_val)

    def __rsub__(self, other):
        if other == 0:
            return self
        else:
            return self.__sub__(other)

    def __getitem__(self, item):
        try:
            return self._distances[item]
        except IndexError:
            print(f"  -IndexError- Last index: {len(self) - 1}")

    def __setitem__(self, key, value):
        try:
            self._distances[key] = value
        except IndexError:
            print(f"  -IndexError- Last index: {len(self) - 1}")

    @property
    def values(self) -> np.ndarray:
        return self._distances

    @staticmethod
    def _load(distances):
        return val2array(distances)

    def sum(self) -> Union[float, int]:
        return round(np.nansum(self._distances), DIST_ROUND)


class SlopeDistances(Distances):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"SlopeDistances({self._distances.round(4)})"

    def to_horizontal(self, vangles):
        _horizontal = slope2hor(self._distances, vangles.values)

        return HorizontalDistances(_horizontal)

    def to_delta(self, vangles: Angles, sh, th):
        _delta = p2p_dh(self._distances,
                        vangles.values,
                        self._load(sh),
                        self._load(th))

        return DeltaDistances(_delta)


class HorizontalDistances(Distances):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"HorizontalDistances({self._distances.round(4)})"

    def to_reference(self, elevation):
        _reference = hor2ref(self._distances, elevation)

        return ReferenceDistances(_reference)


class ReferenceDistances(Distances):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"ReferenceDistances({self._distances.round(4)})"

    def to_egsa(self, k):
        _egsa = ref2egsa(self._distances, k)

        return EGSADistances(_egsa)


class EGSADistances(Distances):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"EGSADistances({self._distances.round(4)})"


class DeltaDistances(Distances):
    def __init__(self, distances):
        super().__init__(distances)

    def __repr__(self):
        return f"DeltaDistances({self._distances.round(4)})"
