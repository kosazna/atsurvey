# -*- coding: utf-8 -*-
from typing import List
from aztool_topo.primitives import *


# def traverse_azimuth(measurements: pd.DataFrame, a_start: float):
#     hold = a_start
#     for i in measurements.itertuples():
#         _a = hold + i.h_angle_fixed + 200
#         if _a > 400:
#             a = round(_a % 400, 6)
#         else:
#             a = round(_a, 6)
#         hold = a
#
#         measurements.loc[i.Index, 'azimuth'] = a


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
        return round(calc_k(self.f2.x, self.f1.x), DIST_ROUND)

    @property
    def info(self):
        out = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [np.nan],
             'horizontal': [np.nan],
             'wx': [np.nan],
             'wy': [np.nan],
             'wz': [np.nan]}, orient='index')

        return out.style.format(traverse_formatter)

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
        h_angle = Angles(self.odeusi['h_angle'])
        dz_temp = DeltaDistances(self.odeusi['dz_temp'])
        h_dist = HorizontalDistances(self.odeusi['h_dist'])
        dz_temp[-1] = np.nan
        h_dist[-1] = np.nan
        ref_dist = h_dist.to_reference(self.mean_elevation)
        egsa_dist = ref_dist.to_egsa(self.k)
        self.length = egsa_dist.sum()

        azimuths = Azimuths(h_angle).for_traverse(self.a_start)
        dx_temp = DeltaDistances(egsa_dist * azimuths.sin)
        dy_temp = DeltaDistances(egsa_dist * azimuths.cos)
        dx = dx_temp
        dy = dy_temp
        dz = dz_temp
        stations = Points.from_traverse(self.f2, self.f2, dx, dy, dz)

        self.odeusi['surf_dist'] = ref_dist.values
        self.odeusi['egsa_dist'] = egsa_dist.values
        self.odeusi['azimuth'] = azimuths.values
        self.odeusi['dX'] = dx.values
        self.odeusi['dY'] = dy.values
        self.odeusi['dZ'] = dz.values
        self.odeusi['X'] = stations.x
        self.odeusi['Y'] = stations.y
        self.odeusi['Z'] = stations.z

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'azimuth',
                'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

        self.odeusi = self.odeusi[keep]

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
        self.a_finish: Azimuth = self.l1.azimuth(self.l2)

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
        return round(calc_k(self.f2.x, self.l1.x), DIST_ROUND)

    @property
    def a_measured(self):
        return Azimuth.from_measurements(self.a_start, self.odeusi['h_angle'])

    @property
    def angular_correction(self):
        return round(self.angular_misclosure / self.odeusi.shape[0],
                     ANGLE_ROUND)

    @property
    def angular_misclosure(self):
        return round(self.a_finish.value - self.a_measured.value, ANGLE_ROUND)

    @property
    def horizontal_misclosure(self):
        return round(np.sqrt(self.wx ** 2 + self.wy ** 2), DIST_ROUND)

    @property
    def wx(self):
        return round(self.l1.x - self._l1_temp_x, DIST_ROUND)

    @property
    def wy(self):
        return round(self.l1.y - self._l1_temp_y, DIST_ROUND)

    @property
    def wz(self):
        return round(self.l1.z - self._l1_temp_z, DIST_ROUND)

    @property
    def x_cor(self):
        try:
            return round(self.wx / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def y_cor(self):
        try:
            return round(self.wy / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def z_cor(self):
        try:
            return round(self.wz / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def info(self):
        out = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]})

        return out.style.format(traverse_formatter).hide_index()

    def compute(self):
        h_angle = Angles(self.odeusi['h_angle'])
        dz_temp = DeltaDistances(self.odeusi['dz_temp'])
        h_dist = HorizontalDistances(self.odeusi['h_dist'])
        dz_temp[-1] = np.nan
        h_dist[-1] = np.nan
        ref_dist = h_dist.to_reference(self.mean_elevation)
        egsa_dist = ref_dist.to_egsa(self.k)
        self.length = egsa_dist.sum()
        h_angle_fixed = h_angle + self.angular_correction
        azimuths = Azimuths(h_angle_fixed).for_traverse(self.a_start)
        dx_temp = DeltaDistances(egsa_dist * azimuths.sin)
        dy_temp = DeltaDistances(egsa_dist * azimuths.cos)
        self._l1_temp_x = self.f2.x + dx_temp.sum()
        self._l1_temp_y = self.f2.y + dy_temp.sum()
        self._l1_temp_z = self.f2.z + dz_temp.sum()
        dx = DeltaDistances(dx_temp + self.x_cor * egsa_dist)
        dy = DeltaDistances(dy_temp + self.y_cor * egsa_dist)
        dz = DeltaDistances(dz_temp + self.z_cor * egsa_dist)
        stations = Points.from_traverse(self.f2, self.l1, dx, dy, dz)

        self.odeusi['surf_dist'] = ref_dist.values
        self.odeusi['egsa_dist'] = egsa_dist.values
        self.odeusi['h_angle_fixed'] = h_angle_fixed.values
        self.odeusi['azimuth'] = azimuths.values
        self.odeusi['dX'] = dx.values
        self.odeusi['dY'] = dy.values
        self.odeusi['dZ'] = dz.values
        self.odeusi['X'] = stations.x
        self.odeusi['Y'] = stations.y
        self.odeusi['Z'] = stations.z

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'h_angle_fixed', 'azimuth',
                'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

        self.odeusi = self.odeusi[keep]

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
        return Azimuth.from_measurements(self.a_start, self.odeusi['h_angle'])

    @property
    def angular_correction(self):
        return round(self.angular_misclosure / self.odeusi.shape[0],
                     ANGLE_ROUND)

    @property
    def angular_misclosure(self):
        return round(self.a_finish.value - self.a_measured.value, ANGLE_ROUND)

    @property
    def horizontal_misclosure(self):
        return round(np.sqrt(self.wx ** 2 + self.wy ** 2), DIST_ROUND)

    @property
    def wx(self):
        return round(self.odeusi['dx_temp'].sum(), DIST_ROUND)

    @property
    def wy(self):
        return round(self.odeusi['dy_temp'].sum(), DIST_ROUND)

    @property
    def wz(self):
        return round(self.odeusi['dz_temp'].sum(), DIST_ROUND)

    @property
    def x_cor(self):
        try:
            return round(self.wx / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def y_cor(self):
        try:
            return round(self.wy / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def z_cor(self):
        try:
            return round(self.wz / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0

    @property
    def info(self):
        out = pd.DataFrame.from_dict(
            {'traverse': [self.name],
             'stations': [self.stops_count],
             'length': [self.length],
             'mean_elev': [self.mean_elevation],
             'angular': [self.angular_misclosure],
             'horizontal': [self.horizontal_misclosure],
             'wx': [self.wx],
             'wy': [self.wy],
             'wz': [self.wz]}, orient='index')

        return out.style.format(traverse_formatter)

    def compute(self):
        h_angle = Angles(self.odeusi['h_angle'])
        dz_temp = DeltaDistances(self.odeusi['dz_temp'])
        h_dist = HorizontalDistances(self.odeusi['h_dist'])
        dz_temp[-1] = np.nan
        h_dist[-1] = np.nan
        ref_dist = h_dist.to_reference(self.mean_elevation)
        egsa_dist = ref_dist.to_egsa(self.k)
        self.length = egsa_dist.sum()
        h_angle_fixed = h_angle + self.angular_correction
        azimuths = Azimuths(h_angle_fixed).for_traverse(self.a_start)
        dx_temp = DeltaDistances(egsa_dist * azimuths.sin)
        dy_temp = DeltaDistances(egsa_dist * azimuths.cos)
        self._l1_temp_x = self.f2.x + dx_temp.sum()
        self._l1_temp_y = self.f2.y + dy_temp.sum()
        self._l1_temp_z = self.f2.z + dz_temp.sum()
        dx = DeltaDistances(dx_temp + self.x_cor * egsa_dist)
        dy = DeltaDistances(dy_temp + self.y_cor * egsa_dist)
        dz = DeltaDistances(dz_temp + self.z_cor * egsa_dist)
        stations = Points.from_traverse(self.f2, self.f2, dx, dy, dz)

        self.odeusi['surf_dist'] = ref_dist.values
        self.odeusi['egsa_dist'] = egsa_dist.values
        self.odeusi['h_angle_fixed'] = h_angle_fixed.values
        self.odeusi['azimuth'] = azimuths.values
        self.odeusi['dX'] = dx.values
        self.odeusi['dY'] = dy.values
        self.odeusi['dZ'] = dz.values
        self.odeusi['X'] = stations.x
        self.odeusi['Y'] = stations.y
        self.odeusi['Z'] = stations.z

        self.odeusi[['bs', 'station', 'fs']] = self.odeusi['angle'].str.split(
            '-', expand=True)

        keep = ['bs', 'station', 'fs',
                'h_dist', 'surf_dist', 'egsa_dist',
                'h_angle', 'h_angle_fixed', 'azimuth',
                'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

        self.odeusi = self.odeusi[keep]

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
