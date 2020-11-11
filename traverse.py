# -*- coding: utf-8 -*-
from typing import List
from .data import *
from .io import *


class OpenTraverse:
    def __init__(self, stops: list,
                 data: pd.DataFrame = None,
                 start: List[Point] = None,
                 working_dir: (str, Path) = None):

        self.name = '-'.join(stops)
        self.working_dir = working_dir

        self.stops = stops
        self.stops_count = len(stops) - 1
        self.length = 0
        self.f1 = start[0] if start else None
        self.f2 = start[1] if start else None
        self.a_start = self.f1.azimuth(self.f2)

        self.metriseis = data.copy()
        self.odeusi = pd.merge(pd.DataFrame(
            list(zip(fmt_angle(stops), fmt_dist(stops))),
            columns=['angle', 'distance']), self.metriseis, on='angle',
            how='left')

        self.stations = None
        self.metrics = None

    @classmethod
    def from_excel(cls, file: (str, Path),
                   stops: list,
                   start: List[Point] = None):
        data = pd.read_excel(file, sheet_name='Traverse_Measurements')
        working_dir = Path(file).parent
        return cls(stops, data, start, working_dir)

    def __repr__(self):
        msg = f"""
            Traverse stops: {'-'.join(self.stops)}  [{self.stops_count}]\n
            Traverse length: {self.length:.3f} m
            Mean Elevation: {self.mean_elevation} m
            k: {self.k:.4f}\n
            α{self.f1.name}-{self.f2.name} : {self.a_start:.4f} g"""

        return msg

    @property
    def mean_elevation(self):
        return round((self.f2.z + self.f1.z) / 2, 3)

    @property
    def k(self):
        return round8(calc_k(self.f2.x, self.f1.x))

    @property
    def info(self):
        io = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [np.nan],
             'horizontal': [np.nan],
             'wx': [np.nan],
             'wy': [np.nan],
             'wz': [np.nan]}, orient='index')

        return io.style.format(traverse_formatter)

    def is_validated(self):
        needed_angles = fmt_angle(self.stops)
        missing = [angle for angle in needed_angles if
                   angle not in self.metriseis['angle'].values]

        if missing:
            print(
                f"\n[ERROR] - Traverse can't be computed:\n  -> {self.name}\n")
            print("Missing angles from measurements:")
            for i in missing:
                print(f'  -> ({i})')
            print('=' * 80, end='\n')
            return False
        return True

    def compute(self):
        # self.odeusi.loc[self.odeusi.index[-1], ['h_dist', 'dz_temp']] = np.nan
        # self.odeusi.loc[self.odeusi.index[-1], 'distance'] = np.nan

        self.odeusi['surf_dist'] = surface_distance(self.odeusi['h_dist'],
                                                    self.mean_elevation)
        self.odeusi['egsa_dist'] = egsa_distance(self.odeusi['surf_dist'],
                                                 self.k)

        self.length = self.odeusi['egsa_dist'].sum()

        self.odeusi['azimuth'] = 0

        hold = self.a_start

        for i in self.odeusi.itertuples():
            _a = hold + i.h_angle + 200
            if _a > 400:
                a = _a % 400
            else:
                a = _a
            hold = a
            self.odeusi.loc[i.Index, 'azimuth'] = a

        self.odeusi['dx_temp'] = self.odeusi['egsa_dist'] * np.sin(
            grad_to_rad(self.odeusi['azimuth']))

        self.odeusi['dy_temp'] = self.odeusi['egsa_dist'] * np.cos(
            grad_to_rad(self.odeusi['azimuth']))

        self.odeusi['dX'] = self.odeusi['dx_temp']
        self.odeusi['dY'] = self.odeusi['dy_temp']
        self.odeusi['dZ'] = self.odeusi['dz_temp']

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'azimuth',
                'dX', 'dY', 'dZ']

        self.odeusi = self.odeusi[keep]

        self.odeusi['X'] = 0
        self.odeusi['Y'] = 0
        self.odeusi['Z'] = 0

        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'] = self.f2.x
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'] = self.f2.y
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'] = self.f2.z

        hold_x = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'][0]
        hold_y = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'][0]
        hold_z = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'][0]
        hold_dx = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dX'][0]
        hold_dy = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dY'][0]
        hold_dz = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dZ'][0]

        for i in self.odeusi.itertuples():
            if i.station == self.f2.name:
                pass
            else:
                hold_x = hold_x + hold_dx
                hold_y = hold_y + hold_dy
                hold_z = hold_z + hold_dz
                self.odeusi.loc[i.Index, 'X'] = round8(hold_x)
                self.odeusi.loc[i.Index, 'Y'] = round8(hold_y)
                self.odeusi.loc[i.Index, 'Z'] = round8(hold_z)
                hold_dx, hold_dy, hold_dz = i.dX, i.dY, i.dZ

        self.metrics = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [np.nan],
             'horizontal': [np.nan],
             'wx': [np.nan],
             'wy': [np.nan],
             'wz': [np.nan]}, orient='index')

        self.stations = Container(self.odeusi[['station', 'X', 'Y', 'Z']])

    def export(self):
        file_to_export = self.odeusi.copy()

        _dir = self.working_dir.joinpath('Traverses')

        if not _dir.exists():
            _dir.mkdir()

        name = '-'.join(self.stops) + f'_{type(self).__name__}'
        file_to_export.round(4).to_excel(_dir.joinpath(f'T_{name}.xlsx'),
                                         index=False)

        self.stations.round(4).to_excel(_dir.joinpath(f'S_{name}.xlsx'))

    def to_shp(self, dst: (str, Path), name: str, round_z=2):
        self.stations.to_shp(dst=dst, name=name, round_z=round_z)

    def to_excel(self, dst: (str, Path), name: str, decimals=4):
        self.stations.to_excel(dst=dst, name=name, decimals=decimals)

    def to_csv(self, dst: (str, Path), name: str, decimals=4, point_id=False):
        self.stations.to_csv(dst=dst, name=name, decimals=decimals,
                             point_id=point_id)


class LinkTraverse(OpenTraverse):
    def __init__(self, stops: list,
                 data: pd.DataFrame = None,
                 start: List[Point] = None,
                 finish: List[Point] = None,
                 working_dir: (str, Path) = '.'):

        super().__init__(stops=stops, data=data, start=start,
                         working_dir=working_dir)

        self.stops_count = len(stops) - 2

        self.l1 = finish[0] if finish else None
        self.l2 = finish[1] if finish else None
        self.a_finish = self.l1.azimuth(self.l2)

        self._l1_temp_x = 0
        self._l1_temp_y = 0
        self._l1_temp_z = 0

    @classmethod
    def from_excel(cls, file: (str, Path),
                   stops: list,
                   start: List[Point] = None,
                   finish: List[Point] = None):
        data = pd.read_excel(file, sheet_name='Traverse_Measurements')
        working_dir = Path(file).parent
        return cls(stops, data, start, finish, working_dir)

    def __repr__(self):
        msg = f"""
            Traverse stops: {'-'.join(self.stops)}  [{self.stops_count}]\n
            Traverse length: {self.length:.3f} m
            Mean Elevation: {self.mean_elevation} m
            k: {self.k:.4f}\n
            α{self.f1.name}-{self.f2.name} : {self.a_start:.4f} g
            α{self.l1.name}-{self.l2.name} : {self.a_finish:.4f} g
            α'{self.l1.name}-{self.l2.name} : {self.a_measured:.4f} g
            Angular Misclosure: {self.angular_misclosure:+.4f} g
            Angular Correction: {self.angular_correction:+.4f} g\n
            Horizontal Misclosure: {self.horizontal_misclosure:.3f} m
            wX: {self.wx:+.3f} m
            wY: {self.wy:+.3f} m
            wZ: {self.wz:+.3f} m"""

        return msg

    @property
    def mean_elevation(self):
        return round((self.f2.z + self.l1.z) / 2, 3)

    @property
    def k(self):
        return round8(calc_k(self.f2.x, self.l1.x))

    @property
    def a_measured(self):
        return azimuth_from_measurements(self.a_start, self.odeusi['h_angle'])

    @property
    def angular_correction(self):
        return round8(self.angular_misclosure / self.odeusi.shape[0])

    @property
    def angular_misclosure(self):
        return round8(self.a_finish - self.a_measured)

    @property
    def horizontal_misclosure(self):
        return round8(np.sqrt(self.wx ** 2 + self.wy ** 2))

    @property
    def wx(self):
        return round8(self.l1.x - self._l1_temp_x)

    @property
    def wy(self):
        return round8(self.l1.y - self._l1_temp_y)

    @property
    def wz(self):
        return round8(self.l1.z - self._l1_temp_z)

    @property
    def x_cor(self):
        try:
            return self.wx / self.length
        except ZeroDivisionError:
            return 0

    @property
    def y_cor(self):
        try:
            return self.wy / self.length
        except ZeroDivisionError:
            return 0

    @property
    def z_cor(self):
        try:
            return self.wz / self.length
        except ZeroDivisionError:
            return 0

    @property
    def info(self):
        io = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]})

        return io.style.format(traverse_formatter).hide_index()

    def compute(self):
        self.odeusi.loc[self.odeusi.index[-1], ['h_dist', 'dz_temp']] = np.nan
        self.odeusi.loc[self.odeusi.index[-1], 'distance'] = np.nan

        self.odeusi['surf_dist'] = surface_distance(self.odeusi['h_dist'],
                                                    self.mean_elevation)
        self.odeusi['egsa_dist'] = egsa_distance(self.odeusi['surf_dist'],
                                                 self.k)

        self.length = self.odeusi['egsa_dist'].sum()

        self.odeusi['h_angle_fixed'] = self.odeusi[
                                           'h_angle'] + self.angular_correction

        self.odeusi['azimuth'] = 0

        traverse_azimuth(self.odeusi, self.a_start)

        self.odeusi['dx_temp'] = self.odeusi['egsa_dist'] * np.sin(
            grad_to_rad(self.odeusi['azimuth']))

        self.odeusi['dy_temp'] = self.odeusi['egsa_dist'] * np.cos(
            grad_to_rad(self.odeusi['azimuth']))

        self._l1_temp_x = self.f2.x + self.odeusi['dx_temp'].sum()
        self._l1_temp_y = self.f2.y + self.odeusi['dy_temp'].sum()
        self._l1_temp_z = self.f2.z + self.odeusi['dz_temp'].sum()

        self.odeusi['dX'] = self.odeusi['dx_temp'] + self.x_cor * self.odeusi[
            'egsa_dist']
        self.odeusi['dY'] = self.odeusi['dy_temp'] + self.y_cor * self.odeusi[
            'egsa_dist']
        self.odeusi['dZ'] = self.odeusi['dz_temp'] + self.z_cor * self.odeusi[
            'egsa_dist']

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'h_angle_fixed', 'azimuth',
                'dX', 'dY', 'dZ']

        self.odeusi = self.odeusi[keep]

        self.odeusi['X'] = 0
        self.odeusi['Y'] = 0
        self.odeusi['Z'] = 0

        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'] = self.f2.x
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'] = self.f2.y
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'] = self.f2.z

        hold_x = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'][0]
        hold_y = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'][0]
        hold_z = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'][0]
        hold_dx = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dX'][0]
        hold_dy = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dY'][0]
        hold_dz = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dZ'][0]

        for i in self.odeusi.itertuples():
            if i.station == self.f2.name:
                pass
            elif i.station == self.l1.name:
                self.odeusi.loc[i.Index, 'X'] = self.l1.x
                self.odeusi.loc[i.Index, 'Y'] = self.l1.y
                self.odeusi.loc[i.Index, 'Z'] = self.l1.z
            else:
                hold_x = hold_x + hold_dx
                hold_y = hold_y + hold_dy
                hold_z = hold_z + hold_dz
                self.odeusi.loc[i.Index, 'X'] = round8(hold_x)
                self.odeusi.loc[i.Index, 'Y'] = round8(hold_y)
                self.odeusi.loc[i.Index, 'Z'] = round8(hold_z)
                hold_dx, hold_dy, hold_dz = i.dX, i.dY, i.dZ

        self.metrics = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]})

        self.stations = Container(self.odeusi[['station', 'X', 'Y', 'Z']])


class ClosedTraverse(OpenTraverse):
    def __init__(self, stops: list,
                 data: pd.DataFrame = None,
                 start: List[Point] = None,
                 working_dir: (str, Path) = '.'):

        super().__init__(stops=stops, data=data, start=start,
                         working_dir=working_dir)

        self.stops_count = len(stops) - 3

        self.a_finish = self.f2.azimuth(self.f1)

        self._l1_temp_x = 0
        self._l1_temp_y = 0
        self._l1_temp_z = 0

    @classmethod
    def from_excel(cls, file: (str, Path),
                   stops: list,
                   start: List[Point] = None):
        data = pd.read_excel(file, sheet_name='Traverse_Measurements')
        working_dir = Path(file).parent
        return cls(stops, data, start, working_dir)

    def __repr__(self):
        msg = f"""
                Traverse stops: {'-'.join(self.stops)}  [{self.stops_count}]\n
                Traverse length: {self.length:.3f} m
                Mean Elevation: {self.mean_elevation} m
                k: {self.k:.4f}\n
                α{self.f1.name}-{self.f2.name} : {self.a_start:.4f} g
                α{self.f2.name}-{self.f1.name} : {self.a_finish:.4f} g
                α'{self.f2.name}-{self.f1.name} : {self.a_measured:.4f} g
                Angular Misclosure: {self.angular_misclosure:+.4f} g
                Angular Correction: {self.angular_correction:+.4f} g\n
                Horizontal Misclosure: {self.horizontal_misclosure:.3f} m
                wX: {self.wx:+.3f} m
                wY: {self.wy:+.3f} m
                wZ: {self.wz:+.3f} m"""

        return msg

    @property
    def a_measured(self):
        return azimuth_from_measurements(self.a_start, self.odeusi['h_angle'])

    @property
    def angular_correction(self):
        return round8(self.angular_misclosure / self.odeusi.shape[0])

    @property
    def angular_misclosure(self):
        return round8(self.a_finish - self.a_measured)

    @property
    def horizontal_misclosure(self):
        return round8(np.sqrt(self.wx ** 2 + self.wy ** 2))

    @property
    def wx(self):
        return round8(self.odeusi['dx_temp'].sum())

    @property
    def wy(self):
        return round8(self.odeusi['dy_temp'].sum())

    @property
    def wz(self):
        return round8(self.odeusi['dz_temp'].sum())

    @property
    def x_cor(self):
        try:
            return self.wx / self.length
        except ZeroDivisionError:
            return 0

    @property
    def y_cor(self):
        try:
            return self.wy / self.length
        except ZeroDivisionError:
            return 0

    @property
    def z_cor(self):
        try:
            return self.wz / self.length
        except ZeroDivisionError:
            return 0

    @property
    def info(self):
        io = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]}, orient='index')

        return io.style.format(traverse_formatter)

    def compute(self):
        self.odeusi.loc[self.odeusi.index[-1], ['h_dist', 'dz_temp']] = np.nan
        self.odeusi.loc[self.odeusi.index[-1], 'distance'] = np.nan

        self.odeusi['surf_dist'] = surface_distance(self.odeusi['h_dist'],
                                                    self.mean_elevation)
        self.odeusi['egsa_dist'] = egsa_distance(self.odeusi['surf_dist'],
                                                 self.k)

        self.length = self.odeusi['egsa_dist'].sum()

        self.odeusi['h_angle_fixed'] = self.odeusi[
                                           'h_angle'] + self.angular_correction

        self.odeusi['azimuth'] = 0

        traverse_azimuth(self.odeusi, self.a_start)

        self.odeusi['dx_temp'] = self.odeusi['egsa_dist'] * np.sin(
            grad_to_rad(self.odeusi['azimuth']))

        self.odeusi['dy_temp'] = self.odeusi['egsa_dist'] * np.cos(
            grad_to_rad(self.odeusi['azimuth']))

        self._l1_temp_x = self.f2.x + self.odeusi['dx_temp'].sum()
        self._l1_temp_y = self.f2.y + self.odeusi['dy_temp'].sum()
        self._l1_temp_z = self.f2.z + self.odeusi['dz_temp'].sum()

        self.odeusi['dX'] = self.odeusi['dx_temp'] + self.x_cor * self.odeusi[
            'egsa_dist']
        self.odeusi['dY'] = self.odeusi['dy_temp'] + self.y_cor * self.odeusi[
            'egsa_dist']
        self.odeusi['dZ'] = self.odeusi['dz_temp'] + self.z_cor * self.odeusi[
            'egsa_dist']

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'h_angle_fixed', 'azimuth',
                'dX', 'dY', 'dZ']

        self.odeusi = self.odeusi[keep]

        self.odeusi['X'] = 0
        self.odeusi['Y'] = 0
        self.odeusi['Z'] = 0

        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'] = self.f2.x
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'] = self.f2.y
        self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'] = self.f2.z

        hold_x = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'X'][0]
        hold_y = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Y'][0]
        hold_z = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'Z'][0]
        hold_dx = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dX'][0]
        hold_dy = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dY'][0]
        hold_dz = self.odeusi.loc[
            self.odeusi['station'] == self.f2.name, 'dZ'][0]

        for i in self.odeusi.itertuples():
            if i.station == self.f2.name:
                pass
            else:
                hold_x = hold_x + hold_dx
                hold_y = hold_y + hold_dy
                hold_z = hold_z + hold_dz
                self.odeusi.loc[i.Index, 'X'] = round8(hold_x)
                self.odeusi.loc[i.Index, 'Y'] = round8(hold_y)
                self.odeusi.loc[i.Index, 'Z'] = round8(hold_z)
                hold_dx, hold_dy, hold_dz = i.dX, i.dY, i.dZ

        self.metrics = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]}, orient='index')

        self.stations = Container(self.odeusi[['station', 'X', 'Y', 'Z']])
