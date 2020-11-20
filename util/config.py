# -*- coding: utf-8 -*-

traverse_formatter = {'length': '{:.3f}',
                      'mean_elev': '{:.3f}',
                      'angular': '{:+.4f}',
                      'horizontal': '{:+.3f}',
                      'wx': '{:+.3f}',
                      'wy': '{:+.3f}',
                      'wz': '{:+.3f}'}

point_formatter = {'X': '{:.3f}',
                   'Y': '{:.3f}',
                   'Z': '{:.3f}'}

ANGLE_ROUND = 8
DIST_ROUND = 8
CORDS_ROUND = 6
EARTH_C = 6371000


def warning(s):
    accepted = s.between(-0.1, 0.1)
    return ['color: red' if not v else '' for v in accepted]
