# -*- coding: utf-8 -*-
from aztool_topo.primitives.angle import *


class Distance:
    def __init__(self, slope=0.0,
                 horizontal=0.0,
                 reference=0.0,
                 egsa=0.0,
                 delta=0.0):
        self._slope = slope
        self._horizontal = horizontal
        self._reference = reference
        self._egsa = egsa
        self._delta = delta

    def __repr__(self):
        msg = f"     Slope: {self._slope:.3f}\n" \
              f"Horizontal: {self._horizontal:.3f}\n" \
              f" Reference: {self._reference:.3f}\n" \
              f"      EGSA: {self._egsa:.3f}"

        return msg

    def get_sd(self):
        return self._slope

    def set_sd(self, other):
        self._slope = other
        self._horizontal = self._reference = self._egsa = self._delta = 0.0

    def get_hd(self):
        return self._horizontal

    def set_hd(self, other):
        self._horizontal = other
        self._slope = self._reference = self._egsa = self._delta = 0.0

    def get_rd(self):
        return self._reference

    def set_rd(self, other):
        self._reference = other
        self._slope = self._horizontal = self._egsa = self._delta = 0.0

    def get_egsa(self):
        return self._egsa

    def set_egsa(self, other):
        self._egsa = other
        self._slope = self._horizontal = self._reference = self._delta = 0.0

    def get_delta(self):
        return self._delta

    def calc_horizontal(self, vangle: Angle):
        if not self._slope:
            raise ValueError("Slope distance is not set")
        self._horizontal = slope2hor(self._slope, vangle.value)

        return self

    def calc_reference(self, elevation):
        if not self._horizontal:
            raise ValueError("Horizontal distance is not set")
        self._reference = hor2ref(self._horizontal, elevation)

        return self

    def calc_egsa(self, k):
        if not self._reference:
            raise ValueError("Reference distance is not set")
        self._egsa = ref2egsa(self._reference, k)

        return self

    def calc_dh(self, vangle: Angle, sh, th):
        if not self._slope:
            raise ValueError("Slope distance is not set")
        self._delta = p2p_dh(self._slope, vangle.value, sh, th)

        return self

    def calc_all(self, vangle, elevation, k):
        self.calc_horizontal(vangle)
        self.calc_reference(elevation)
        self.calc_egsa(k)

        return self


class Distances:
    def __init__(self, distances):
        # self._slope = self._load(slope)
        # self._horizontal = self._load(horizontal)
        # self._reference = self._load(reference)
        # self._egsa = self._load(egsa)
        # self._delta = self._load(delta)
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
        if distances is None:
            return None
        if isinstance(distances, (pd.Series, Distances)):
            return distances.values
        elif isinstance(distances, np.ndarray):
            return distances
        elif isinstance(distances, list):
            return np.array(distances)
        else:
            raise TypeError(f"Unsupported init type: {type(distances)}")

    def sum(self):
        return round(np.nansum(self._distances), DIST_ROUND)

    # def get_sd(self):
    #     return self._slopes
    #
    # def set_sd(self, other):
    #     self._slope = self._load(other)
    #     self._horizontal = self._reference = self._egsa = self._delta = None
    #
    # def get_hd(self):
    #     return self._horizontal
    #
    # def set_hd(self, other):
    #     self._horizontal = self._load(other)
    #     self._slope = self._reference = self._egsa = self._delta = None
    #
    # def get_rd(self):
    #     return self._reference
    #
    # def set_rd(self, other):
    #     self._reference = self._load(other)
    #     self._slope = self._horizontal = self._egsa = self._delta = None
    #
    # def get_egsa(self):
    #     return self._egsa
    #
    # def set_egsa(self, other):
    #     self._egsa = self._load(other)
    #     self._slope = self._horizontal = self._reference = self._delta = None
    #
    # def get_delta(self):
    #     return self._delta
    #
    # def calc_horizontal(self, vangles: Angles):
    #     if self._slope is None:
    #         raise ValueError("Slope distance is not set")
    #     self._horizontal = slope2hor(self._slope, vangles.values)
    #
    #     return self
    #
    # def calc_reference(self, elevation):
    #     if self._horizontal is None:
    #         raise ValueError("Horizontal distance is not set")
    #     self._reference = hor2ref(self._horizontal, elevation)
    #
    #     return self
    #
    # def calc_egsa(self, k):
    #     if self._reference is None:
    #         raise ValueError("Reference distance is not set")
    #     self._egsa = ref2egsa(self._reference, k)
    #
    #     return self
    #
    # def calc_dh(self, vangles: Angles, sh, th):
    #     if self._slope is None:
    #         raise ValueError("Slope distance is not set")
    #
    #     self._delta = p2p_dh(self._slope,
    #                          vangles.values,
    #                          self._load(sh),
    #                          self._load(th))
    #
    #     return self
    #
    # def calc_all(self, vangles: Angles, elevation, k):
    #     self.calc_horizontal(vangles)
    #     self.calc_reference(elevation)
    #     self.calc_egsa(k)
    #
    #     return self


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
