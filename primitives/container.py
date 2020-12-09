# -*- coding: utf-8 -*-

from atsurvey.primitives.point import *
from typing import Tuple


# noinspection PyTypeChecker
def transform_split(data: Union[str, pd.DataFrame, None]) \
        -> Tuple[pd.DataFrame, pd.Series]:
    if data is None:
        df = pd.DataFrame(columns=['station', 'X', 'Y', 'Z'])
    else:
        if isinstance(data, (str, Path)):
            df = pd.read_excel(data)
        else:
            df = data.copy()

    if df.index.name == 'station':
        df.reset_index(inplace=True)

    if not df.empty:
        df['obj'] = df.apply(lambda p: Point(p['station'],
                                             p['X'],
                                             p['Y'],
                                             p['Z']), axis=1)
    else:
        df['obj'] = np.nan

    df.set_index('station', drop=True, inplace=True)
    s = df['obj'].copy(deep=True)

    return df, s


class Container:
    def __init__(self, data: Union[str, pd.DataFrame, None] = None):
        self._data, self._series = transform_split(data)

    def __len__(self) -> int:
        return self._data.shape[0]

    def __getitem__(self, key: str) -> Union[Point, NonePoint]:
        try:
            return self._series[key]
        except KeyError:
            print(f"\n[ERROR] - Point doesn't exist: [{key}]\n")
            return NonePoint()

    def __setitem__(self, key: str, value: Point):
        self._series[key] = value

    def __contains__(self, item: Union[str, list, tuple]) -> bool:
        if isinstance(item, str):
            return item in self._data.index
        elif isinstance(item, (list, tuple)):
            return all([i in self._data.index for i in item])

    def __add__(self, other):
        _original = self._data.copy(deep=True).reset_index()
        _new = other.data.reset_index()

        _final = _original.append(_new).drop_duplicates(subset='station')

        return Container(_final)

    def __radd__(self, other):
        if other == 0:
            return self
        else:
            return self.__add__(other)

    def __iter__(self):
        return iter(self._series)

    @property
    def empty(self) -> bool:
        return self.data.empty

    @property
    def data(self) -> pd.DataFrame:
        keep = ['X', 'Y', 'Z']
        return self._data[keep].copy()

    @property
    def boundaries(self) -> Tuple[int, int, int, int]:
        xmin = int(np.floor(self.data['X'].min()))
        ymin = int(np.floor(self.data['Y'].min()))
        xmax = int(np.ceil(self.data['X'].max()))
        ymax = int(np.ceil(self.data['Y'].max()))

        return xmin, ymin, xmax, ymax

    def sort(self):
        self._data, self._series = transform_split(self._data.sort_index())

        return self

    def update(self, other: pd.DataFrame):
        _original = self._data.copy(deep=True).reset_index()
        _new = other.copy().reset_index()

        _final = _original.append(_new).drop_duplicates(subset='station')

        self._data, self._series = transform_split(_final)

        return self

    def to_shp(self, dst: Union[str, Path], name: str, round_z: int = 2):
        if self.empty:
            print("Can't export empty data Container")
        else:
            export_shp(data=self.data, dst=dst, name=name,
                       round_display_z=round_z)

    def to_excel(self, dst: Union[str, Path], name: str, decimals: int = 4):
        if self.empty:
            print("Can't export empty data Container")
        else:
            _dst = Path(dst).joinpath(f'{name}.xlsx')
            self.data.rename_axis('ID').round(decimals).to_excel(_dst)

    def to_csv(self, dst: Union[str, Path],
               name: str,
               decimals: int = 4,
               point_id: bool = False):
        if self.empty:
            print("Can't export empty data Container")
        else:
            _dst = Path(dst).joinpath(f'{name}.csv')
            self.data.round(decimals).to_csv(_dst, header=False, index=point_id)
