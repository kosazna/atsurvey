# -*- coding: utf-8 -*-
from aztool_topo.util.config import *
import pandas as pd
import json
from datetime import datetime
from pathlib import Path


def timestamp():
    return datetime.now().strftime('%d/%m/%Y %H:%M:%S')


def fmt_angle(stops):
    joined_stops = []
    for i, stop in enumerate(stops):
        if i == 0:
            pass
        else:
            try:
                joined_stops.append(f'{stops[i - 1]}-{stop}-{stops[i + 1]}')
            except IndexError:
                pass

    return joined_stops


def fmt_dist(stops):
    joined_stops = []
    for i, stop in enumerate(stops):
        if i == 0:
            pass
        else:
            try:
                joined_stops.append(f'{stop}-{stops[i + 1]}')
            except IndexError:
                pass

    return joined_stops


def extract_workind_dir(data):
    if isinstance(data, str):
        _path = Path(data)
        return _path if _path.is_dir() else _path.parent
    elif isinstance(data, Path):
        return data if data.is_dir() else data.parent
    else:
        raise IsADirectoryError("""Working directory can't be infered from data.
        Provide 'working_dir' when instantiating the class SurveyProject.""")


def parse_stops(stationsstr, keep=0):
    _stations = stationsstr.split('-')

    if keep == 1:
        return _stations[:2]
    elif keep == -1:
        return _stations[-2:]
    else:
        return _stations


def styler(data: pd.DataFrame, formatter: dict):
    return data.style.format(formatter).apply(warning,
                                              subset=['angular'])


def load_json(path):
    """
    Loads json file to a dictionary.

    :param path: str
        Path of json file.
    :return: dict
        Python dictionary of the json file.
    """

    try:
        with open(path, "r") as status_f:
            data = json.load(status_f)
        return data
    except IOError:
        print(f'\n!! NO SUCH FILE : {path}\n')


def write_json(path, data):
    """
    Writes python dictionary to a json file (indent=2).

    :param path: str
        Path to write the json file.
    :param data: dict
        Python dictionary.
    :return: Nothing
    """

    with open(path, "w") as p_file:
        json.dump(data, p_file, indent=2)
