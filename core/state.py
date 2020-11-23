# -*- coding: utf-8 -*-
import pickle
from aztool_topo.util.paths import *
from aztool_topo.util.misc import *


class ATTProjectState:
    def __init__(self, project=None):
        self._paths = ATTPaths()
        self._history = self._load()
        self._project = project
        self._project_wd = self._project.wd.uwd
        self._output_name = f"{self._project.name}.attp"
        self._backup_name = f"{timestamp()}-{self._project.name}.attp"
        self._output = self._project_wd.joinpath(
            self._output_name)
        self._backup = self._paths.att_folder.joinpath(
            self._output_name)

    def _load(self):
        if self._paths.att_projects.exists():
            with open(self._paths.att_projects, "r") as history:
                _history = json.load(history)
            return _history
        else:
            return dict()

    def save(self):
        self._history[self._project.name] = {
            "last_save": timestamp(),
            "date_created": self._project.time,
            "directory": str(self._project_wd)
        }

        write_json(self._paths.att_projects, self._history)

        with open(str(self._output), 'wb') as azttp:
            pickle.dump(self._project, azttp)

        with open(str(self._backup), 'wb') as azttp:
            pickle.dump(self._project, azttp)

        self._history = self._load()

    def update(self, project):
        self._project = project

    def load(self, project_path):
        with open(project_path, 'rb') as azttp:
            self._project = pickle.load(azttp)

        return self._project
