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

ATT_JSON = "attps.json"
ATT_PROJECT_FILES = ".ATTFiles"
ATT_PROJECT_EXT = ".attp"
ATT_FILE_EXT = ".attf"
ATT_FILE_MAP_EXT = ".attm"
XLS_EXTS = [".xls", ".xlsx"]


def warning(s):
    accepted = s.between(-0.1, 0.1)
    return ['color: red' if not v else '' for v in accepted]
