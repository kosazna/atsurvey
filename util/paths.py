# -*- coding: utf-8 -*-
from pathlib import Path
from atsurvey.util.config import *
from typing import Union


class ATTPaths:
    def __init__(self, directory: Union[str, Path, None] = None):
        self.userhome = Path.home()
        self.att_projects = self.userhome.joinpath(ATT_JSON)
        self.att_folder = self.userhome.joinpath(ATT_PROJECT_FILES)
        self._check_att_folder_exists()

        self.uwd = None
        self.uwd_folder = None
        self._init_paths(directory)

    def _init_paths(self, directory: Union[str, Path, None]):
        if directory is None:
            self.uwd = self.userhome
            self.uwd_folder = self.att_folder
        else:
            self.uwd = Path(directory)
            self.uwd_folder = self.uwd.joinpath(".attFiles")
            if not self.uwd_folder.exists():
                self.uwd_folder.mkdir(parents=True, exist_ok=True)

    def _check_att_folder_exists(self):
        if not self.att_folder.exists():
            self.att_folder.mkdir(parents=True, exist_ok=True)
