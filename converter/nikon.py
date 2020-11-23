# -*- coding: utf-8 -*-
import numpy as np
from typing import Union
from aztool_topo.util.io import *


class NikonRawConverter:
    def __init__(self, file: Union[str, Path] = None):
        self.filepath = Path(file)
        self.wd = self.filepath.parent
        self.basename = self.filepath.stem
        self.raw = load_data(self.filepath,
                             skiprows=1,
                             names=range(7),
                             header=None)

        self.out_xlsx = self.wd.joinpath(f'{self.basename}_Converted.xlsx')
        self.out_pickle = self.wd.joinpath(f'{self.basename}_Converted.attm')

        self.processed = pd.DataFrame()
        self.stations = pd.DataFrame()
        self.sideshots = pd.DataFrame()
        self.all = pd.DataFrame()
        self.convert_map = dict()

    @staticmethod
    def meas_type(fs: str, h_angle: float):
        if fs[0].isalpha() and h_angle == 0.0:
            return 'backsight'
        elif fs[0].isalpha():
            return 'station'
        else:
            return 'sideshot'

    def transform(self):
        to_keep = ['OB', 'SS', 'LS', '--Target Generic Prism: "My Prism"',
                   '--Target Reflectorless: "My Reflectorless"']

        df = self.raw[self.raw[0].isin(to_keep)]

        df['midenismos'] = ''
        df['stasi'] = df[1].str.extract('OP([a-zA-Z]+[0-9]+)')[0]
        df['metrisi'] = df[2].str.extract('FP([a-zA-Z0-9]+)')[0]
        df['orizontia'] = df[3].str.extract(r'AR(\d+\.\d+)')[0].astype(float)
        df['katakorifi'] = df[4].str.extract(r'ZE(\d+\.\d+)')[0].astype(float)
        df['apostasi'] = df[5].str.extract(r'SD(\d+\.\d+)')[0].astype(float)
        df['us'] = df[1].str.extract(r'HR:(\d+\.\d+)')[0].astype(float)
        df['uo'] = df[1].str.extract(r'HI(\d+\.\d+)')[0].astype(float)
        df.loc[(df[0] == 'OB') & (df['orizontia'] == 0), 'midenismos'] = df.loc[
            (df[0] == 'OB') & (df['orizontia'] == 0), 'metrisi']

        df2 = df[
            [0, 'midenismos', 'stasi', 'metrisi', 'orizontia', 'katakorifi',
             'apostasi', 'us', 'uo']]

        df2.columns = ['meas_type', 'bs', 'station', 'fs', 'h_angle', 'v_angle',
                       'slope_dist', 'target_h', 'station_h']

        df2['bs'].replace('', np.nan, inplace=True)
        df2['bs'].fillna(method='ffill', inplace=True)

        df2['station_h'].replace(0, np.nan, inplace=True)
        df2['target_h'].replace(0, np.nan, inplace=True)

        df2['station_h'].fillna(method='ffill', inplace=True)
        df2['target_h'].fillna(method='ffill', inplace=True)

        df2['station'].fillna('<NA>', inplace=True)

        self.processed = df2.loc[
            df2['station'].str.contains('^[a-zA-Z]+[0-9]+', regex=True)].copy()

        self.processed.reset_index(inplace=True, drop=True)

        self.processed['meas_type'] = self.processed.apply(
            lambda x: self.meas_type(x['fs'], x['h_angle']), axis=1)

        self.processed.loc[
            self.processed['meas_type'] == 'midenismos', 'bs'] = '-'
        self.processed["mid"] = np.arange(1, self.processed.shape[0] + 1,
                                          dtype=np.uint16)

        self.processed = self.processed[
            ['mid', 'meas_type', 'bs', 'station', 'fs', 'h_angle', 'v_angle',
             'slope_dist', 'target_h', 'station_h']]

        self.processed = self.processed.astype({'meas_type': pd.StringDtype(),
                                                'bs': pd.StringDtype(),
                                                'station': pd.StringDtype(),
                                                'fs': pd.StringDtype()})

        indexes_to_delete = []

        search = self.processed.loc[
            self.processed['meas_type'] == 'backsight'].copy()

        search.reset_index(inplace=True)

        for i in search.itertuples():
            try:
                if i.station == search.loc[i.Index + 1, 'station'] and i.fs == \
                        search.loc[i.Index + 1, 'fs']:
                    if i.index + 1 == search.loc[i.Index + 1, 'index']:
                        indexes_to_delete.append(i.index)
            except KeyError:
                pass

        self.all = self.processed.drop(indexes_to_delete)

        self.stations = self.all.loc[
            self.processed['fs'].str.contains('^[a-zA-Z]+[0-9]+', regex=True)]

        self.sideshots = self.all.loc[
            self.processed['fs'].str.contains(r'^\d+', regex=True)]

        self.convert_map = {'all': self.all,
                            'stations': self.stations,
                            'sideshots': self.sideshots,
                            'raw': self.processed}

    def export_xlsx(self):
        with pd.ExcelWriter(self.out_xlsx) as writer:
            for name, df in self.convert_map.items():
                df.to_excel(writer, sheet_name=name, index=False)

    def export_pickle(self):
        with open(self.out_pickle, 'wb') as pkl_file:
            pickle.dump(self.convert_map, pkl_file)
