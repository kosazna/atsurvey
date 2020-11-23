# -*- coding: utf-8 -*-
from aztool_topo.primitives import *


class TraverseFormatter:
    def __init__(self, data, file: Union[str, Path] = None,
                 sheet_name: str = 'stations'):
        # self.filepath = Path(file)
        # self.wd = self.filepath.parent
        # self.basename = self.filepath.stem
        self.df = load_data(data)
        self.angles = None
        self.dists = None

        # self.out_xlsx = self.wd.joinpath(f'{self.basename}_Transformed.xlsx')
        # self.out_pickle = self.wd.joinpath(f'{self.basename}_Transformed.attf')

        self._traverse = None

    @staticmethod
    def join_stops_for_angle(midenismos, stasi, metrisi):
        return '-'.join([midenismos, stasi, metrisi])

    @staticmethod
    def join_stops_for_dist(station, fs):
        return '-'.join(sorted([station, fs]))

    def get_data(self):
        return self._traverse.copy()

    def tranform(self):
        self.df.fillna('<NA>', inplace=True)

        self.df['angle'] = self.df.apply(
            lambda x: self.join_stops_for_angle(x.bs, x.station, x.fs),
            axis=1)

        self.df['dist'] = self.df.apply(
            lambda x: self.join_stops_for_dist(x['station'], x['fs']), axis=1)

        self.angles = self.df['angle'].values
        self.dists = self.df['dist'].values

        s_dist = SlopeDistances(self.df['slope_dist'])
        h_dist = s_dist.to_horizontal(self.df['v_angle'])
        dz_temp = s_dist.to_delta(self.df['v_angle'],
                                  self.df['station_h'],
                                  self.df['target_h'])

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

    # def export(self):
    #     with pd.ExcelWriter(self.out_xlsx) as writer:
    #         self.traverse.round(6).to_excel(writer,
    #                                         sheet_name='Traverse_Measurements',
    #                                         index=False)
    #
    #         self.final.round(6).to_excel(writer, sheet_name='Processed_Data',
    #                                      index=False)
