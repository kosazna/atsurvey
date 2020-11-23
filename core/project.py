# -*- coding: utf-8 -*-
from aztool_topo.core.traverse import *
from aztool_topo.core.sideshot import *
from aztool_topo.core.state import *
from functools import partial


class SurveyProject:
    def __init__(self,
                 name: str = None,
                 data: Any = None,
                 traverses: Any = None,
                 known_points: Any = None,
                 working_dir: Union[str, Path] = None):
        self.name = name
        self.time = timestamp()
        self.wd = ATTPaths(working_dir)

        self.data = load_data(data)
        self.traverse_list = load_data(traverses)
        self.known = load_data(known_points)

        self.stations = Container(self.known)
        self.sideshots = Container()

        self.c_traverses = []
        self.c_traverses_count = 0
        self.c_traverses_info = None
        self.c_sideshots = []
        self.c_sideshots_count = 0

        self.state = ATTProjectState(self)
        self.pdgui = None

    @staticmethod
    def open(project_name):
        with open(ATTPaths().att_projects, "r") as history:
            _history = json.load(history)

        _dir = Path(_history[project_name]['directory'])
        _filename = _dir.joinpath(f"{project_name}.{ATT_PROJECT_EXT}")

        with open(_filename, 'rb') as azttp:
            _project = pickle.load(azttp)

        return _project

    def save(self):
        self.state.save()

    @classmethod
    def from_excel_file(cls, file, project_name=None):
        _path = Path(file)
        _name = _path.stem if project_name is None else project_name
        _all_data = pd.ExcelFile(_path)
        _data = _all_data.parse('measurements')
        _traverses = _all_data.parse('traverses')
        _known_points = _all_data.parse('known_points')
        _working_dir = _path.parent

        return cls(name=_name,
                   data=_data,
                   traverses=_traverses,
                   known_points=_known_points,
                   working_dir=_working_dir)

    def point2obj(self, points: Union[list, tuple]) -> List[Point]:
        return [self.stations[points[0]], self.stations[points[1]]]

    def compute_traverses(self):
        self.c_traverses = []
        self.c_traverses_count = 0
        self.c_traverses_info = None
        for traverse in self.traverse_list.itertuples():
            if traverse.compute == 1:
                if traverse.t_type == 'LinkTraverse':
                    tr = LinkTraverse(stops=parse_stops(traverse.stations),
                                      data=self.data,
                                      start=self.point2obj(
                                          parse_stops(traverse.stations, 1)),
                                      finish=self.point2obj(
                                          parse_stops(traverse.stations, -1)),
                                      working_dir=self.wd.uwd)
                elif traverse.t_type == 'ClosedTraverse':
                    tr = ClosedTraverse(stops=parse_stops(self.stations),
                                        data=self.data,
                                        start=self.point2obj(
                                            parse_stops(traverse.stations, 1)),
                                        working_dir=self.wd.uwd)
                else:
                    tr = OpenTraverse(stops=parse_stops(traverse.stations),
                                      data=self.data,
                                      start=self.point2obj(
                                          parse_stops(traverse.stations, 1)),
                                      working_dir=self.wd.uwd)

                if tr.is_validated:
                    tr.compute()
                else:
                    pass  # TODO: add warnings

                    self.c_traverses.append(tr)

        if self.c_traverses:
            self.c_traverses_info = pd.concat(
                [trav.metrics for trav in self.c_traverses]).reset_index(
                drop=True)

            self.c_traverses_info.index = self.c_traverses_info.index + 1

            self.stations = self.stations + sum(
                [trav.stations for trav in self.c_traverses])

            self.c_traverses_count = len(self.c_traverses)

            self.state.update(self)

            return styler(self.c_traverses_info, traverse_formatter)
        else:
            print("\nNo traverse was computed")

    def compute_sideshots(self, exclude=None):
        def exclusion(group_check, items):
            return not bool(set(group_check).intersection(items))

        self.c_sideshots = []
        self.c_sideshots_count = 0

        all_groups = self.data.groupby(['station', 'bs'])

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
            self.state.update(self)
        else:
            print('No sideshots were computed')

    def export_traverses(self):
        _out = self.wd.uwd.joinpath('Project_Traverses.xlsx')

        with pd.ExcelWriter(_out) as writer:
            self.c_traverses_info.round(4).to_excel(writer, sheet_name='Info')

            for i, traverse in enumerate(self.c_traverses, 1):
                traverse.traverse.round(4).to_excel(writer,
                                                    index=False,
                                                    sheet_name=str(i))

        self.stations.to_shp(self.wd.uwd, "Project_Stations")

    def export_sideshots(self, csv_point_id=False):
        self.sideshots.to_excel(self.wd.uwd, "Project_Sideshots")
        self.sideshots.to_csv(self.wd.uwd, "Project_Sideshots",
                              point_id=csv_point_id)
        self.sideshots.to_shp(self.wd.uwd, "Project_Sideshots")

    def edit(self):
        from pandasgui import show
        traverses = self.traverse_list
        measurements = self.data
        known_points = self.stations.data
        sideshots = self.sideshots.data

        self.pdgui = show(traverses,
                          measurements,
                          known_points,
                          sideshots)

    def save_changes(self):
        self.stations = Container(self.pdgui.get_dataframes()['known_points'])
        self.traverse_list = self.pdgui.get_dataframes()['traverses']
        self.data = self.pdgui.get_dataframes()['measurements']
        self.sideshots = Container(self.pdgui.get_dataframes()['sideshots'])
