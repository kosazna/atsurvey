# -*- coding: utf-8 -*-
from typing import List, Tuple
from aztool_topo.primitives import *
from aztool_topo.util.paths import *
from aztool_topo.converter.formater import TraverseFormatter


class Traverse:
    def __init__(self, stops: list,
                 data: Any,
                 start: List[Point],
                 finish: List[Point] = None,
                 working_dir: Union[str, Path] = None):
        self.name = self.name = '-'.join(stops)
        self.wd = ATTPaths(working_dir)
        self.stops = stops
        self.stops_count = 0
        self.length = 0
        self.f1 = start[0]
        self.f2 = start[1]
        self.l1 = finish[0] if finish is not None else NonePoint()
        self.l2 = finish[1] if finish is not None else NonePoint()
        self.a_start: Azimuth = self.f1.azimuth(self.f2)
        self.a_finish: Azimuth = self.l1.azimuth(self.l2) if not isinstance(
            self.l1, NonePoint) else Azimuth(0)
        self.stations = None
        self.metrics = None
        self._l1_temp_x = 0
        self._l1_temp_y = 0
        self._l1_temp_z = 0
        self.data = load_data(data)
        self.formatted = TraverseFormatter(self.pick_data()).tranform()
        self.traverse = self.formatted.get_data()
        self.is_validated, self.missing = self.validate()
        self.has_mids = False
        self.mids = self._init_mids()

    def __repr__(self) -> str:
        msg = f"Traverse stops: {'-'.join(self.stops)}\n" \
              f"Stops count: {self.stops_count:12}\n" \
              f"Traverse length: {self.length:.3f} m\n" \
              f"Mean Elevation: {self.mean_elevation:} m\n" \
              f"k: {self.k:.4f}\n\n" \
              f"α{self.f1.name}-{self.f2.name} : {self.a_start:.4f} g\n" \
              f"α{self.l1.name}-{self.l2.name} : {self.a_finish:.4f} g\n" \
              f"α'{self.l1.name}-{self.l2.name} : {self.a_measured:.4f} g\n" \
              f"Angular Misclosure: {self.angular_misclosure:.4f} g\n" \
              f"Angular Correction: {self.angular_correction:.4f} g\n\n" \
              f"Horizontal Misclosure: {self.horizontal_misclosure:.3f} m\n" \
              f"wX: {self.wx:.3f} m\n" \
              f"wY: {self.wy:.3f} m\n" \
              f"wZ: {self.wz:.3f} m"

        return msg

    def pick_data(self) -> pd.DataFrame:
        _picked = self.data.loc[(self.data['bs'].isin(self.stops)) & (
            self.data['station'].isin(self.stops)) & (
                                    self.data['fs'].isin(self.stops))].copy()

        return _picked

    def _init_mids(self) -> list:
        if 'mid' in self.traverse.columns:
            self.has_mids = True
            return self.traverse['mid'].to_list()
        else:
            return [np.nan] * self.traverse.shape[0]

    @classmethod
    def from_template(cls, file: Union[str, Path],
                      stops: list,
                      start: List[Point],
                      finish: List[Point] = None):
        data = pd.read_excel(file, sheet_name='all')
        working_dir = Path(file).parent
        return cls(stops, data, start, finish, working_dir)

    @property
    def mean_elevation(self) -> float:
        if isinstance(self, LinkTraverse):
            return round((self.f2.z + self.l1.z) / 2, 3)
        return round((self.f2.z + self.f1.z) / 2, 3)

    @property
    def k(self) -> float:
        if isinstance(self, LinkTraverse):
            return round(calc_k(self.f2.x, self.l1.x), DIST_ROUND)
        return round(calc_k(self.f2.x, self.f1.x), DIST_ROUND)

    @property
    def a_measured(self) -> Azimuth:
        return Azimuth.from_measurements(self.a_start,
                                         self.traverse['h_angle'])

    @property
    def angular_misclosure(self) -> float:
        if self.a_finish:
            return round(self.a_finish.value - self.a_measured.value,
                         ANGLE_ROUND)
        return 0.0

    @property
    def angular_correction(self) -> float:
        return round(self.angular_misclosure / self.traverse.shape[0],
                     ANGLE_ROUND)

    @property
    def wx(self) -> float:
        if isinstance(self.l1, NonePoint):
            return 0.0
        return round(self.l1.x - self._l1_temp_x, DIST_ROUND)

    @property
    def wy(self) -> float:
        if isinstance(self.l1, NonePoint):
            return 0.0
        return round(self.l1.y - self._l1_temp_y, DIST_ROUND)

    @property
    def wz(self) -> float:
        if isinstance(self.l1, NonePoint):
            return 0.0
        return round(self.l1.z - self._l1_temp_z, DIST_ROUND)

    @property
    def horizontal_misclosure(self) -> float:
        return round(np.sqrt(self.wx ** 2 + self.wy ** 2), DIST_ROUND)

    @property
    def x_cor(self) -> float:
        try:
            return round(self.wx / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0.0

    @property
    def y_cor(self) -> float:
        try:
            return round(self.wy / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0.0

    @property
    def z_cor(self) -> float:
        try:
            return round(self.wz / self.length, DIST_ROUND)
        except ZeroDivisionError:
            return 0.0

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

    def validate(self) -> Tuple[bool, list]:
        needed_angles = fmt_angle(self.stops)
        missing = [angle for angle in needed_angles if
                   angle not in self.formatted.angles]

        if missing:
            print(
                f"\n[ERROR] - Traverse can't be computed:\n  -> {self.name}\n")
            print("Missing angles from measurements:")
            for i in missing:
                print(f'  -> ({i})')
            print('=' * 80, end='\n')
            return False, missing
        return True, missing

    def export(self):
        file_to_export = self.traverse.copy()

        _dir = self.wd.uwd_folder

        name = '-'.join(self.stops) + f'_{type(self).__name__}'
        file_to_export.round(4).to_excel(_dir.joinpath(f'T_{name}.xlsx'),
                                         index=False)

        self.stations.round(4).to_excel(_dir.joinpath(f'S_{name}.xlsx'))

    def to_shp(self, dst: Union[str, Path], name: str, round_z: int = 2):
        self.stations.to_shp(dst=dst, name=name, round_z=round_z)

    def to_excel(self, dst: Union[str, Path], name: str, decimals: int = 4):
        self.stations.to_excel(dst=dst, name=name, decimals=decimals)

    def to_csv(self,
               dst: Union[str, Path],
               name: str,
               decimals: int = 4,
               point_id: bool = False):
        self.stations.to_csv(dst=dst, name=name, decimals=decimals,
                             point_id=point_id)


class OpenTraverse(Traverse):
    def __init__(self, stops: list,
                 data: pd.DataFrame,
                 start: List[Point],
                 finish: List[Point] = None,
                 working_dir: Union[str, Path] = None):
        super().__init__(stops=stops,
                         data=data,
                         start=start,
                         finish=finish,
                         working_dir=working_dir)
        self.stops_count = len(stops) - 1

    def compute(self):
        if self.is_validated:
            h_angle = Angles(self.traverse['h_angle'])
            dz_temp = DeltaDistances(self.traverse['dz_temp'])
            h_dist = HorizontalDistances(self.traverse['h_dist'])
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

            self.traverse['surf_dist'] = ref_dist.values
            self.traverse['egsa_dist'] = egsa_dist.values
            self.traverse['azimuth'] = azimuths.values
            self.traverse['dX'] = dx.values
            self.traverse['dY'] = dy.values
            self.traverse['dZ'] = dz.values
            self.traverse['X'] = stations.x
            self.traverse['Y'] = stations.y
            self.traverse['Z'] = stations.z

            if self.has_mids:
                keep = ['mid', 'bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']
            else:
                keep = ['bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

            self.traverse = self.traverse[keep]

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

            self.stations = Container(self.traverse[['station', 'X', 'Y', 'Z']])


class LinkTraverse(Traverse):
    def __init__(self, stops: list,
                 data: pd.DataFrame,
                 start: List[Point],
                 finish: List[Point],
                 working_dir: (str, Path) = None):
        super().__init__(stops=stops,
                         data=data,
                         start=start,
                         finish=finish,
                         working_dir=working_dir)
        self.stops_count = len(stops) - 2

    def compute(self):
        if self.is_validated:
            h_angle = Angles(self.traverse['h_angle'])
            dz_temp = DeltaDistances(self.traverse['dz_temp'])
            h_dist = HorizontalDistances(self.traverse['h_dist'])
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

            self.traverse['surf_dist'] = ref_dist.values
            self.traverse['egsa_dist'] = egsa_dist.values
            self.traverse['h_angle_fixed'] = h_angle_fixed.values
            self.traverse['azimuth'] = azimuths.values
            self.traverse['dX'] = dx.values
            self.traverse['dY'] = dy.values
            self.traverse['dZ'] = dz.values
            self.traverse['X'] = stations.x
            self.traverse['Y'] = stations.y
            self.traverse['Z'] = stations.z

            if self.has_mids:
                keep = ['mid', 'bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'h_angle_fixed', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']
            else:
                keep = ['bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'h_angle_fixed', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

            self.traverse = self.traverse[keep]

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

            self.stations = Container(self.traverse[['station', 'X', 'Y', 'Z']])


class ClosedTraverse(Traverse):
    def __init__(self, stops: list,
                 data: pd.DataFrame,
                 start: List[Point],
                 finish: List[Point] = None,
                 working_dir: (str, Path) = None):
        super().__init__(stops=stops,
                         data=data,
                         start=start,
                         finish=finish,
                         working_dir=working_dir)
        self.stops_count = len(stops) - 3

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

    def compute(self):
        if self.is_validated:
            h_angle = Angles(self.traverse['h_angle'])
            dz_temp = DeltaDistances(self.traverse['dz_temp'])
            h_dist = HorizontalDistances(self.traverse['h_dist'])
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

            self.traverse['surf_dist'] = ref_dist.values
            self.traverse['egsa_dist'] = egsa_dist.values
            self.traverse['h_angle_fixed'] = h_angle_fixed.values
            self.traverse['azimuth'] = azimuths.values
            self.traverse['dX'] = dx.values
            self.traverse['dY'] = dy.values
            self.traverse['dZ'] = dz.values
            self.traverse['X'] = stations.x
            self.traverse['Y'] = stations.y
            self.traverse['Z'] = stations.z

            if self.has_mids:
                keep = ['mid', 'bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'h_angle_fixed', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']
            else:
                keep = ['bs', 'station', 'fs',
                        'h_dist', 'surf_dist', 'egsa_dist',
                        'h_angle', 'h_angle_fixed', 'azimuth',
                        'dX', 'dY', 'dZ', 'X', 'Y', 'Z']

            self.traverse = self.traverse[keep]

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

            self.stations = Container(self.traverse[['station', 'X', 'Y', 'Z']])
