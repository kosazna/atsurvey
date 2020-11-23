# -*- coding: utf-8 -*-

from pathlib import Path


class ATTPaths:
    def __init__(self, directory=None):
        self.userhome = Path.home()
        self.uwd = self.userhome if directory is None else Path(directory)
        self.att_projects = self.userhome.joinpath("attps.json")
        self.att_folder = self.userhome.joinpath("aztool_topo.files")
        self._check_aztt_folder_exists()
        self.uwd_traverses = self.uwd.joinpath('Traverses')

    def _check_aztt_folder_exists(self):
        if not self.att_folder.exists():
            self.att_folder.mkdir(parents=True, exist_ok=True)
