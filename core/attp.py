# -*- coding: utf-8 -*-

from aztool_topo.core.project import *
import pickle


class AZTTP:
    PROJECTS = Path.home().joinpath("azttps.json")

    def __init__(self, project: SurveyProject = None):
        self._history = self._load()
        self._project = project
        self._output_name = f"{self._project.name}.azttp" if project is not None else ''
        self._output = self._project.working_dir.joinpath(
            self._output_name) if project is not None else ''

    @staticmethod
    def _load():
        if AZTTP.PROJECTS.exists():
            with open(AZTTP.PROJECTS, "r") as history:
                _history = json.load(history)
            return _history
        else:
            return dict()

    def save(self):
        self._history[self._project.name] = {
            "date_created": self._project.time,
            "working_dir": str(self._project.working_dir)
        }

        write_json(AZTTP.PROJECTS, self._history)

        with open(str(self._output), 'wb') as azttp:
            pickle.dump(self._project, azttp)

    def load(self, project_path):
        with open(project_path, 'rb') as azttp:
            self._project = pickle.load(azttp)

        return self._project
