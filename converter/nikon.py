# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from pathlib import Path


class NikonRawConverter:
    def __init__(self, file: str = None):
        self.working_dir = Path(file).parent
        self.basename = Path(file).stem
        self.output = self.working_dir.joinpath(
            f'{self.basename}_Converted.xlsx')
        self.raw = pd.read_csv(file, skiprows=1, names=range(7), header=None)
        self.cleaned = None
        self.staseis = None
        self.taximetrika = None
        self.stats = None
        self.final = None

    @staticmethod
    def meas_type(fs: str, h_angle: float):
        if fs[0].isalpha() and h_angle == 0.0:
            return 'midenismos'
        elif fs[0].isalpha():
            return 'stasi'
        else:
            return 'taximetriko'

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

        self.cleaned = df2.loc[
            df2['station'].str.contains('^[a-zA-Z]+[0-9]+', regex=True)].copy()

        self.cleaned.reset_index(inplace=True, drop=True)

        self.cleaned['meas_type'] = self.cleaned.apply(
            lambda x: self.meas_type(x['fs'], x['h_angle']), axis=1)

        self.cleaned.loc[self.cleaned['meas_type'] == 'midenismos', 'bs'] = '-'
        self.cleaned["mid"] = np.arange(1, self.cleaned.shape[0] + 1)

        self.cleaned = self.cleaned[
            ['mid', 'meas_type', 'bs', 'station', 'fs', 'h_angle', 'v_angle',
             'slope_dist', 'target_h', 'station_h']]

        indexes_to_delete = []

        search = self.cleaned.loc[
            self.cleaned['meas_type'] == 'midenismos'].copy()

        search.reset_index(inplace=True)

        for i in search.itertuples():
            try:
                if i.station == search.loc[i.Index + 1, 'station'] and i.fs == \
                        search.loc[i.Index + 1, 'fs']:
                    if i.index + 1 == search.loc[i.Index + 1, 'index']:
                        indexes_to_delete.append(i.index)
            except KeyError:
                pass

        self.final = self.cleaned.drop(indexes_to_delete)

        self.staseis = self.final.loc[
            self.cleaned['fs'].str.contains('^[a-zA-Z]+[0-9]+', regex=True)]

        self.taximetrika = self.final.loc[
            self.cleaned['fs'].str.contains(r'^\d+', regex=True)]

        self.stats = self.taximetrika.groupby('station', as_index=False)[
            'fs'].count().sort_values(by='fs')
        self.stats['sunola'] = self.stats['fs'].cumsum()

    def export(self):
        with pd.ExcelWriter(self.output) as writer:
            self.final.to_excel(writer, sheet_name=f'All', index=False)

            self.staseis.to_excel(writer, sheet_name=f'Staseis', index=False)

            self.taximetrika.to_excel(writer, sheet_name=f'Taximetrika',
                                      index=False)

            self.stats.to_excel(writer, sheet_name=f'Statistics',
                                index=False)

            self.cleaned.to_excel(writer, sheet_name=f'RAW_cleaned',
                                  index=False)
