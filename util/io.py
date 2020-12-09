# -*- coding: utf-8 -*-
import pandas as pd
import pickle
from pathlib import Path
from typing import Union, Any
from atsurvey.util.config import *


def load_data(data: Union[str, Path, pd.DataFrame],
              **kwargs: Any):
    if isinstance(data, (str, Path)):
        _file = Path(data)
        _ext = _file.suffix

        if _ext in [ATT_PROJECT_EXT, ATT_FILE_EXT]:
            return pd.read_pickle(_file)
        elif _ext == ATT_FILE_MAP_EXT:
            with open(_file, 'rb') as pkl_file:
                return pickle.load(pkl_file)['all']
        elif _ext in XLS_EXTS:
            return pd.read_excel(_file, **kwargs)
        elif _ext == ".csv":
            return pd.read_csv(_file, **kwargs)
        else:
            raise TypeError(f"Can't load file type: {_ext}")
    elif isinstance(data, pd.DataFrame):
        return data.copy()
    else:
        raise TypeError(f"Can't load data: {data}")


def export_shp(data: pd.DataFrame,
               dst: Union[str, Path],
               name: str,
               round_display_z: int = 2):
    import geopandas as gpd
    _data = data.copy().reset_index().rename(columns={'station': 'ID'}).round(4)
    _data['ID'] = _data['ID'].astype(str)
    _data['display_Z'] = _data['Z'].round(round_display_z).astype(str)
    _geometry = gpd.points_from_xy(_data['X'], _data['Y'], _data['Z'])
    gdf = gpd.GeoDataFrame(_data, geometry=_geometry)

    output = Path(dst).joinpath(f'{name}.shp')

    gdf.to_file(output)
