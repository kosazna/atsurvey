# -*- coding: utf-8 -*-
from aztool_topo.primitives.angle import *


class Distance:
    def __init__(self, slope=0.0, horizontal=0.0, reference=0.0, egsa=0.0):
        self._slope = slope
        self._horizontal = horizontal
        self._reference = reference
        self._egsa = egsa
        self._dh = 0.0

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
        self._horizontal = self._reference = self._egsa = self._dh = 0.0

    def get_hd(self):
        return self._horizontal

    def set_hd(self, other):
        self._horizontal = other
        self._slope = self._reference = self._egsa = self._dh = 0.0

    def get_rd(self):
        return self._reference

    def set_rd(self, other):
        self._reference = other
        self._slope = self._horizontal = self._egsa = self._dh = 0.0

    def get_egsa(self):
        return self._egsa

    def set_egsa(self, other):
        self._egsa = other
        self._slope = self._horizontal = self._reference = self._dh = 0.0

    def get_dh(self):
        return self._dh

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
        self._dh = p2p_dh(self._slope, vangle.value, sh, th)

        return self

    def calc_all(self, vangle, elevation, k):
        self.calc_horizontal(vangle)
        self.calc_reference(elevation)
        self.calc_egsa(k)

        return self


class Distances:
    def __init__(self, slope=None, horizontal=None, reference=None, egsa=None):
        self._slope = self._load(slope)
        self._horizontal = self._load(horizontal)
        self._reference = self._load(reference)
        self._egsa = self._load(egsa)
        self._dh = None

    def __repr__(self):
        msg = f"     Slope: {self._slope.round(3)}\n" \
              f"Horizontal: {self._horizontal.round(3)}\n" \
              f" Reference: {self._reference.round(3)}\n" \
              f"      EGSA: {self._egsa.round(3)}"

        return msg

    @staticmethod
    def _load(distances):
        if distances is None:
            return None
        if isinstance(distances, pd.Series):
            return distances.values
        elif isinstance(distances, np.ndarray):
            return distances
        elif isinstance(distances, list):
            return np.array(distances)
        else:
            raise TypeError(f"Unsupported init type: {type(distances)}")

    def get_sd(self):
        return self._slope

    def set_sd(self, other):
        self._slope = self._load(other)
        self._horizontal = self._reference = self._egsa = self._dh = None

    def get_hd(self):
        return self._horizontal

    def set_hd(self, other):
        self._horizontal = self._load(other)
        self._slope = self._reference = self._egsa = self._dh = None

    def get_rd(self):
        return self._reference

    def set_rd(self, other):
        self._reference = self._load(other)
        self._slope = self._horizontal = self._egsa = self._dh = None

    def get_egsa(self):
        return self._egsa

    def set_egsa(self, other):
        self._egsa = self._load(other)
        self._slope = self._horizontal = self._reference = self._dh = None

    def get_dh(self):
        return self._dh

    def calc_horizontal(self, vangles: Angles):
        if self._slope is None:
            raise ValueError("Slope distance is not set")
        self._horizontal = slope2hor(self._slope, vangles.values)

        return self

    def calc_reference(self, elevation):
        if self._horizontal is None:
            raise ValueError("Horizontal distance is not set")
        self._reference = hor2ref(self._horizontal, elevation)

        return self

    def calc_egsa(self, k):
        if self._reference is None:
            raise ValueError("Reference distance is not set")
        self._egsa = ref2egsa(self._reference, k)

        return self

    def calc_dh(self, vangles: Angles, sh, th):
        if self._slope is None:
            raise ValueError("Slope distance is not set")

        self._dh = p2p_dh(self._slope,
                          vangles.values,
                          self._load(sh),
                          self._load(th))

        return self

    def calc_all(self, vangles: Angles, elevation, k):
        self.calc_horizontal(vangles)
        self.calc_reference(elevation)
        self.calc_egsa(k)

        return self
