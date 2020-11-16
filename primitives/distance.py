# -*- coding: utf-8 -*-
from aztool_topo.primitives.angle import *


class Distance:
    def __init__(self, distance):
        self._distance = distance

    def __repr__(self):
        return f"Distance({self._distance:.4f})"

    def __len__(self):
        return 1

    def __add__(self, other):
        if isinstance(other, Distance):
            _val = self.value + other.value
        elif isinstance(other, (float, int)):
            _val = self.value + other
        else:
            raise TypeError(f"Unsupported addition type: {type(other)}")

        return Distance(_val)

    def __sub__(self, other):
        if isinstance(other, Distance):
            _val = self.value - other.value
        elif isinstance(other, (float, int)):
            _val = self.value - other
        else:
            raise TypeError(f"Unsupported subtraction type: {type(other)}")

        return Distance(_val)

    @property
    def value(self):
        return self._distance

    def sum(self):
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

    def __len__(self):
        return len(self._distances)

    def __add__(self, other):
        if isinstance(other, np.ndarray):
            _other = other
        elif isinstance(other, (pd.Series, Distances)):
            _other = other.values
        else:
            _other = np.array(other)

        return self._distances + _other

    def __mul__(self, other):
        _deltas = self._distances * other
        return _deltas

    @property
    def values(self):
        return self._distances

    @staticmethod
    def _load(distances):
        return val2array(distances, Distances)

    def sum(self):
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
