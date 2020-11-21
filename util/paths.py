# -*- coding: utf-8 -*-

from pathlib import Path


class AZTTPaths:
    def __init__(self, directory=None):
        self.userhome = Path.home()
        self.uwd = self.userhome if directory is None else Path(directory)
        self.aztt_projects = self.userhome.joinpath("attps.json")
        self.aztt_folder = self.userhome.joinpath("aztool_topo.files")
        self._check_aztt_folder_exists()
        self.uwd_traverses = self.uwd.joinpath('Traverses')

    def _check_aztt_folder_exists(self):
        if not self.aztt_folder.exists():
            self.aztt_folder.mkdir(parents=True, exist_ok=True)
