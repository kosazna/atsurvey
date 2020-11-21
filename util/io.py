# -*- coding: utf-8 -*-
import pandas as pd
import pickle
from shutil import copy
from pathlib import Path
from aztool_topo.util.config import *


def load_data(data, **kwargs):
    if isinstance(data, (str, Path)):
        _file = Path(data)
        _ext = _file.suffix

        if _ext in [AZT_PROJECT_EXT, AZT_FILE_EXT]:
            return pd.read_pickle(_file)
        elif _ext == AZT_FILE_MAP_EXT:
            with open(_file, 'rb') as pkl_file:
                return pickle.load(pkl_file)
        elif _ext in XLS_EXTS:
            # _sheet = 0 if sheet_name is None else sheet_name
            return pd.read_excel(_file, **kwargs)
        elif _ext == ".csv":
            return pd.read_csv(_file, **kwargs)
        else:
            raise TypeError(f"Can't load file type: {_ext}")
    elif isinstance(data, pd.DataFrame):
        return data
    else:
        raise TypeError(f"Can't load data: {data}")


def copy_shp(file: (str, Path), dst: (str, Path)):
    _file = Path(file)
    copy(_file, dst)
    copy(_file.with_suffix('.dbf'), dst)
    copy(_file.with_suffix('.shx'), dst)


def export_shp(data: pd.DataFrame, dst: (str, Path), name: str, round_z=2):
    import geopandas as gpd
    _data = data.copy().reset_index().rename(columns={'station': 'ID'}).round(4)
    _data['ID'] = _data['ID'].astype(str)
    _data['display_Z'] = _data['Z'].round(round_z).astype(str)
    _geometry = gpd.points_from_xy(_data['X'], _data['Y'], _data['Z'])
    gdf = gpd.GeoDataFrame(_data, geometry=_geometry)

    output = Path(dst).joinpath(f'{name}.shp')

    gdf.to_file(output)
