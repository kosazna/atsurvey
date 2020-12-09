# -*- coding: utf-8 -*-
from atsurvey.primitives import *


class TraverseFormatter:
    def __init__(self, data: Any):
        self.df = load_data(data)
        self.angles = None
        self.dists = None
        self._traverse = None

    @staticmethod
    def join_stops_for_angle(midenismos, stasi, metrisi) -> str:
        return '-'.join([midenismos, stasi, metrisi])

    @staticmethod
    def join_stops_for_dist(station, fs) -> str:
        return '-'.join(sorted([station, fs]))

    def get_data(self) -> pd.DataFrame:
        return self._traverse.copy()

    def tranform(self):
        self.df.fillna('<NA>', inplace=True)

        s_dist = SlopeDistances(self.df['slope_dist'])
        h_dist = s_dist.to_horizontal(self.df['v_angle'])
        dz_temp = s_dist.to_delta(self.df['v_angle'],
                                  self.df['station_h'],
                                  self.df['target_h'])

        self.df['angle'] = self.df.apply(
            lambda x: self.join_stops_for_angle(x.bs, x.station, x.fs),
            axis=1)

        self.df['dist'] = self.df.apply(
            lambda x: self.join_stops_for_dist(x.station, x.fs),
            axis=1)

        self.angles = self.df['angle'].values
        self.dists = self.df['dist'].values

        self.df['stop_dist'] = h_dist.values
        miki = self.df.groupby('dist')['stop_dist'].mean()
        self.df['h_dist'] = self.df['dist'].map(miki)

        self.df['stop_dh'] = dz_temp.values
        self.df['abs_dh'] = abs(self.df['stop_dh'])
        dz = self.df.groupby('dist')['abs_dh'].mean()
        self.df['abs_avg_dh'] = self.df['dist'].map(dz)
        self.df['dz_temp'] = mean_dh_signed(self.df['stop_dh'],
                                            self.df['abs_avg_dh'])

        self._traverse = self.df.loc[
            self.df['h_angle'] != 0, ['mid', 'bs', 'station', 'fs',
                                      'h_angle', 'h_dist', 'dz_temp', ]]

        return self
