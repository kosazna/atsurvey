# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from aztool_topo.util.config import *


def vectorize(func):
    def wrapper(*args, **kwargs):
        vector = False

        for i in args:
            if isinstance(i, (np.ndarray, pd.Series)):
                vector = True
                break

        if not vector:
            for i in kwargs:
                if isinstance(kwargs[i], (np.ndarray, pd.Series)):
                    vector = True
                    break

        if vector:
            vfunc = np.vectorize(func)
        else:
            vfunc = func

        result = vfunc(*args, **kwargs)

        return result

    return wrapper


def calc_k(x1, x2):
    x_sum = x1 + x2
    _ = (12311 * ((((x_sum / 2) * (10 ** -6)) - 0.5) ** 2) - 400) * (10 ** -6)
    return round(1 + _, DIST_ROUND)


@vectorize
def grad2rad(angle):
    return round((angle * np.pi) / 200, ANGLE_ROUND)


@vectorize
def rad2grad(angle):
    return round((angle * 200) / np.pi, ANGLE_ROUND)


@vectorize
def slope2hor(distance, angle):
    return round(distance * np.sin(grad2rad(angle)), DIST_ROUND)


@vectorize
def hor2ref(distance, mean_elevation):
    return round(distance * (EARTH_C / (EARTH_C + mean_elevation)), DIST_ROUND)


@vectorize
def ref2egsa(distance, k=0.9996):
    return round(distance * k, DIST_ROUND)


@vectorize
def p2p_dh(distance, angle, uo, us):
    return round(distance * np.cos(grad2rad(angle)) + uo - us, DIST_ROUND)


@vectorize
def calc_X(init_x, distance, azimuth):
    return round(init_x + distance * np.sin(grad2rad(azimuth)), CORDS_ROUND)


@vectorize
def calc_Y(init_y, distance, azimuth):
    return round(init_y + distance * np.cos(grad2rad(azimuth)), CORDS_ROUND)


@vectorize
def calc_Z(init_z, distance, angle, uo, us):
    return round(init_z + p2p_dh(distance, angle, uo, us), CORDS_ROUND)


@vectorize
def resolve_angle(angle):
    if 0 <= angle <= 400:
        return round(angle, ANGLE_ROUND)
    elif angle > 400:
        return round(angle % 400, ANGLE_ROUND)
    else:
        return round(angle + abs(angle // 400) * 400, ANGLE_ROUND)
