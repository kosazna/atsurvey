# -*- coding: utf-8 -*-
from atsurvey.primitives.angle import *


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

    def for_traverse(self, a_start):
        _azimuths = [a_start]
        for idx, angle in enumerate(self._anglesG):
            _azimuth = Angle(_azimuths[idx] + angle + 200)
            _azimuths.append(_azimuth)

        return Azimuths(_azimuths[1:])
