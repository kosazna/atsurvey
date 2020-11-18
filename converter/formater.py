# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from aztool_topo.util.topofuncs import slope2hor, p2p_dh, mean_dh_signed


class TraverseFormatter:
    def __init__(self, file: (str, Path) = None, sheet_name: str = 'Staseis'):
        self.working_dir = Path(file).parent
        self.basename = Path(file).stem
        self.output = self.working_dir.joinpath(
            f'{self.basename}_Transformed.xlsx')
        self.df = pd.read_excel(file, sheet_name=sheet_name)
        self.final = None
        self.odeusi = None

    @staticmethod
    def join_stops_for_angle(midenismos, stasi, metrisi):
        return '-'.join([midenismos, stasi, metrisi])

    @staticmethod
    def join_stops_for_dist(station, fs):
        return '-'.join(sorted([station, fs]))

    def tranform(self):
        self.df.fillna('<NA>', inplace=True)

        self.df['angle'] = self.df.apply(
            lambda x: self.join_stops_for_angle(x.bs, x.station, x.fs),
            axis=1)

        self.df['dist'] = self.df.apply(
            lambda x: self.join_stops_for_dist(x['station'], x['fs']), axis=1)

        self.df['stop_dist'] = slope2hor(self.df.slope_dist,
                                         self.df.v_angle)

        miki = self.df.groupby('dist')['stop_dist'].mean()

        self.df['h_dist'] = self.df['dist'].map(miki)

        self.df['stop_dh'] = p2p_dh(self.df.slope_dist,
                                    self.df.v_angle,
                                    self.df.station_h,
                                    self.df.target_h)

        self.df['abs_dh'] = abs(self.df['stop_dh'])

        dz = self.df.groupby('dist')['abs_dh'].mean()

        self.df['abs_avg_dh'] = self.df['dist'].map(dz)

        self.df['dz_temp'] = mean_dh_signed(self.df['stop_dh'],
                                            self.df['abs_avg_dh'])

        self.final = self.df[
            ['mid', 'meas_type', 'bs', 'station', 'fs', 'h_angle', 'v_angle',
             'slope_dist', 'target_h', 'station_h',
             'stop_dist', 'stop_dh', 'angle', 'dist', 'h_dist',
             'abs_avg_dh', 'dz_temp']]

        self.odeusi = self.df.loc[
            self.df['h_angle'] != 0, ['mid', 'angle', 'dist', 'h_angle',
                                      'h_dist', 'dz_temp', ]].copy()

    def export(self):
        with pd.ExcelWriter(self.output) as writer:
            self.odeusi.round(6).to_excel(writer,
                                          sheet_name='Traverse_Measurements',
                                          index=False)

            self.final.round(6).to_excel(writer, sheet_name='Processed_Data',
                                         index=False)
