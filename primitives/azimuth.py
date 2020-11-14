# -*- coding: utf-8 -*-
from aztool_topo.primitives.angle import *


class Azimuth(Angle):
    def __init__(self, angle):
        super().__init__(angle)

    def __repr__(self):
        return f"Azimuth({self._angleG:.4f})"

    @classmethod
    @vectorize
    def from_tuples(cls, a, b, reverse=False):
        dx = b[0] - a[0]
        dy = b[1] - a[1]

        _azimuth = Angle(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.value)

    @classmethod
    @vectorize
    def from_points(cls, a, b, reverse=False):
        dx = b.x - a.x
        dy = b.y - a.y

        _azimuth = Angle(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.value)

    @classmethod
    def from_measurements(cls, a_start, measurements):
        if isinstance(a_start, Angle):
            _a_start = a_start
        else:
            _a_start = Angle(a_start)

        if isinstance(measurements, float):
            _meas = Angle(measurements)
        elif isinstance(measurements, (Angle, Angles)):
            _meas = measurements
        else:
            _meas = Angles(measurements)

        _azimuth = _a_start.value + _meas.sum() + len(_meas) * 200

        return cls(_azimuth)

    @staticmethod
    def traverse(measurements: pd.DataFrame, a_start: float):
        hold = a_start
        for i in measurements.itertuples():
            _a = hold + i.h_angle_fixed + 200
            if _a > 400:
                a = round(_a % 400, 6)
            else:
                a = round(_a, 6)
            hold = a

            measurements.loc[i.Index, 'azimuth'] = a


class Azimuths(Angles):
    def __init(self, angles):
        super().__init__(angles)

    def __repr__(self):
        return f"Azimuths({self._anglesG.round(4)})"

    @classmethod
    def from_tuples(cls, a, b, reverse=False):
        dx = np.array([i[0] for i in b]) - np.array([i[0] for i in a])
        dy = np.array([i[1] for i in b]) - np.array([i[1] for i in a])

        _azimuth = Angles(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.values)

    @classmethod
    def from_points(cls, a, b, reverse=False):
        dx = np.array([i.x for i in b]) - np.array([i.x for i in a])
        dy = np.array([i.y for i in b]) - np.array([i.y for i in a])

        _azimuth = Angles(determine_quartile(dx, dy))

        if reverse:
            return cls(_azimuth.reverse)
        else:
            return cls(_azimuth.values)

    @classmethod
    def from_measurements(cls, a_start, measurements):
        if isinstance(a_start, Angle):
            _a_start = a_start
        else:
            _a_start = Angle(a_start)

        if isinstance(measurements, Angles):
            _meas = measurements
        else:
            _meas = Angles(measurements)

        _azimuth = _a_start.value + _meas.values + 200

        return cls(_azimuth)

    def traverse(self,  a_start):
        pass
