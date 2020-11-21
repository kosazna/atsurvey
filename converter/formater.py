# -*- coding: utf-8 -*-
from aztool_topo.converter.nikon import *
from aztool_topo.util.topofuncs import slope2hor, p2p_dh, mean_dh_signed


class NikonTraverseFormatter:
    def __init__(self, file: Union[str, Path] = None,
                 sheet_name: str = 'stations'):
        self.filepath = Path(file)
        self.wd = self.filepath.parent
        self.basename = self.filepath.stem
        self.df = load_data(self.filepath, sheet_name=sheet_name)

        self.out_xlsx = self.wd.joinpath(f'{self.basename}_Transformed.xlsx')
        self.out_pickle = self.wd.joinpath(f'{self.basename}_Transformed.attf')

        self.final = None
        self.traverse = None

    @classmethod
    def from_converter(cls, converter: NikonRawConverter):
        pass

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

        self.traverse = self.df.loc[
            self.df['h_angle'] != 0, ['mid', 'angle', 'dist', 'h_angle',
                                      'h_dist', 'dz_temp', ]].copy()

        return self

    def export(self):
        with pd.ExcelWriter(self.out_xlsx) as writer:
            self.traverse.round(6).to_excel(writer,
                                            sheet_name='Traverse_Measurements',
                                            index=False)

            self.final.round(6).to_excel(writer, sheet_name='Processed_Data',
                                         index=False)
