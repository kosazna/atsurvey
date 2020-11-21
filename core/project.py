# -*- coding: utf-8 -*-
from aztool_topo.core.traverse import *
from aztool_topo.core.taximetria import *
from aztool_topo.core.project_logger import *
from functools import partial


class SurveyProject:
    def __init__(self,
                 name: str = None,
                 traverse_data: (str, pd.DataFrame) = None,
                 sideshot_data: (str, pd.DataFrame) = None,
                 traverses: (str, pd.DataFrame) = None,
                 known_points: (str, pd.DataFrame) = None,
                 working_dir: (str, Path) = None):

        self.name = name
        self.time = timestamp()
        self.pwd = AZTTPaths(working_dir)

        self.t_data = load_data(traverse_data)
        self.s_data = load_data(sideshot_data)
        self.t_list = load_data(traverses)

        self.stations = Container(load_data(known_points))
        self.sideshots = Container()

        self.c_traverses = []
        self.c_traverses_count = 0
        self.c_traverses_info = None

        self.c_sideshots = []
        self.c_sideshots_count = 0

        self.logger = AZTTPLogger(self)

    @staticmethod
    def open(project_name):
        with open(AZTTPaths().aztt_projects, "r") as history:
            _history = json.load(history)

        _dir = Path(_history[project_name]['directory'])
        _filename = _dir.joinpath(f"{project_name}.azttp")

        with open(_filename, 'rb') as azttp:
            _project = pickle.load(azttp)

        return _project

    def save(self):
        self.logger.save()

    @classmethod
    def from_single_file(cls, file, project_name=None):
        _path = Path(file)
        _name = _path.stem if project_name is None else project_name
        _all_data = pd.ExcelFile(_path)
        _traverse_data = _all_data.parse('Traverse_Measurements')
        _sideshot_data = _all_data.parse('Taximetrika')
        _traverses = _all_data.parse('Traverses')
        _known_points = _all_data.parse('Known_Points')
        _working_dir = _path.parent

        return cls(name=_name,
                   traverse_data=_traverse_data,
                   sideshot_data=_sideshot_data,
                   traverses=_traverses,
                   known_points=_known_points,
                   working_dir=_working_dir)

    def point2obj(self, points: Union[list, tuple]) -> List[Point]:
        return [self.stations[points[0]], self.stations[points[1]]]

    def compute_traverses(self):
        self.c_traverses = []
        for traverse in self.t_list.itertuples():
            if traverse.compute == 1:
                if traverse.t_type == 'LinkTraverse':
                    tr = LinkTraverse(stops=parse_stops(traverse.stations),
                                      data=self.t_data,
                                      start=self.point2obj(
                                          parse_stops(traverse.stations, 1)),
                                      finish=self.point2obj(
                                          parse_stops(traverse.stations, -1)),
                                      working_dir=self.pwd.uwd)
                elif traverse.t_type == 'ClosedTraverse':
                    tr = ClosedTraverse(stops=parse_stops(self.stations),
                                        data=self.t_data,
                                        start=self.point2obj(
                                            parse_stops(traverse.stations, 1)),
                                        working_dir=self.pwd.uwd)
                else:
                    tr = OpenTraverse(stops=parse_stops(traverse.stations),
                                      data=self.t_data,
                                      start=self.point2obj(
                                          parse_stops(traverse.stations, 1)),
                                      working_dir=self.pwd.uwd)

                if tr.is_validated():
                    tr.compute()

                    self.c_traverses.append(tr)

        if self.c_traverses:
            self.c_traverses_info = pd.concat(
                [trav.metrics for trav in self.c_traverses]).reset_index(
                drop=True)

            self.c_traverses_info.index = self.c_traverses_info.index + 1

            self.stations = self.stations + sum(
                [trav.stations for trav in self.c_traverses])

            self.c_traverses_count = len(self.c_traverses)

            self.logger.update(self)

            return styler(self.c_traverses_info, traverse_formatter)
        else:
            print("\nNo traverse was computed")

    def compute_sideshots(self, exclude=None):
        def exclusion(group_check, items):
            return not bool(set(group_check).intersection(items))

        self.c_sideshots = []

        all_groups = self.s_data.groupby(['station', 'bs'])

        if exclude is None:
            point_groups = list(all_groups.groups)
        else:
            if isinstance(exclude, str):
                _exclude = [exclude]
            else:
                _exclude = exclude

            part_exclusion = partial(exclusion, items=_exclude)
            point_groups = list(filter(part_exclusion, all_groups.groups))

        for group in point_groups:
            if group in self.stations:
                _data = all_groups.get_group(group)

                ss = Sideshot(_data,
                              self.stations[group[0]],
                              self.stations[group[1]])

                ss.compute()

                self.c_sideshots.append(ss)

        if self.c_sideshots:
            self.sideshots = sum([s.points for s in self.c_sideshots])
            self.sideshots.sort()
            self.c_sideshots_count = len(self.sideshots)

            print(f"[{self.c_sideshots_count}] points were calculated.")
            self.logger.update(self)
        else:
            print('No sideshots were computed')

    def export_traverses(self):
        _out = self.pwd.uwd.joinpath('Project_Traverses.xlsx')

        with pd.ExcelWriter(_out) as writer:
            self.c_traverses_info.round(4).to_excel(writer, sheet_name='Info')

            for i, traverse in enumerate(self.c_traverses, 1):
                traverse.traverse.round(4).to_excel(writer,
                                                    index=False,
                                                    sheet_name=str(i))

        self.stations.to_shp(self.pwd.uwd, "Project_Stations")

    def export_sideshots(self, csv_point_id=False):
        self.sideshots.to_excel(self.pwd.uwd, "Project_Sideshots")
        self.sideshots.to_csv(self.pwd.uwd, "Project_Sideshots",
                              point_id=csv_point_id)
        self.sideshots.to_shp(self.pwd.uwd, "Project_Sideshots")

    def edit(self):
        from pandasgui import show
        known_points = self.stations.data
        traverses = self.t_list
        traverse_data = self.t_data
        sideshot_data = self.s_data
        sideshots = self.sideshots.data

        _data = show(known_points,
                     traverses,
                     traverse_data,
                     sideshot_data,
                     sideshots)
