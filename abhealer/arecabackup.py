# -*- coding: utf-8 -*-

'''
This module contained a series classes that use for maintain informations of
Areca Backup.
'''

import pathlib
import arrow
import xml.etree.ElementTree as etree
from . import abhealer


def folder_to_int(name):
    parts = name.split("_")
    first_part = int(parts[0])
    if len(parts) < 2:
        second_part = 0
    else:
        second_part = int(parts[1])

    return first_part * 1000 + second_part


def int_to_folder(aint):
    first_part = aint // 1000
    second_part = aint % 1000

    second_part_text = ""
    if second_part > 0:
        second_part_text = "_%s" % second_part

    return str(first_part) + second_part_text


class DataInfo(object):
    DIR_SUFFIX = "_data"

    def __init__(self, adir):
        self._base_dir = adir

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def datetime(self):
        value = str(int(self))
        return arrow.Arrow(
            int(value[:4]),
            int(value[4:6]),
            int(value[6:8]),
            int(value[8:10]),
            int(value[10:12]),
            0,
            int(value[12:]),
        ).datetime

    def _name_without_suffix(self):
        return self.base_dir.name[:-len(self.DIR_SUFFIX)]

    def __repr__(self):
        return "%s(%s)" % (type(self).__qualname__, int(self))

    def __int__(self):
        return folder_to_int(self._name_without_suffix())


class Project(object):

    def __init__(self, repository, cfg, adir):
        self._base_dir = pathlib.Path(adir)
        self._repository = repository
        self._cfg = cfg

    @property
    def repository(self):
        return self._repository

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def name(self):
        return self.base_dir.name

    @property
    def data_infos(self):
        infos = []
        for subdir in self.base_dir.iterdir():
            if not subdir.name.endswith(DataInfo.DIR_SUFFIX):
                continue

            infos.append(DataInfo(subdir))

        infos = sorted(infos, key=lambda x: int(x))

        return infos

    def __repr__(self):
        return "%s(\"%s\")" % (type(self).__qualname__, self.name)


class Repository(object):
    CFG_DIR_NAME = "areca_config_backup"

    def __init__(self, adir):
        self._base_dir = pathlib.Path(adir)

        # Validate directory
        self._cfg_dir = self._base_dir / self.CFG_DIR_NAME
        if not self._cfg_dir.exists():
            msg = ("'%s' directory not found ! The directory "
                   "is not an Areca Backup repository: %s!")
            msg = msg % (self.CFG_DIR_NAME, self._base_dir)
            raise NotADirectoryError(msg)

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def cfg_dir(self):
        return self._cfg_dir

    @property
    def projects(self):

        all_projects = []
        for subdir in self.base_dir.iterdir():
            if subdir.name == self.CFG_DIR_NAME:
                continue

            history_path = subdir / "history"
            if (not history_path.exists()) or (not history_path.is_file()):
                abhealer.logger().warn(
                    "Found invalid project : %s" % subdir.name)
                continue

            project_cfg_path = self.cfg_dir / (subdir.name + ".bcfg")
            all_projects.append(Project(
                self, etree.parse(str(project_cfg_path)), subdir))

        return all_projects


class ArecaBackup(object):
    '''
    The class use for maintain Areca Backup's behaviors.
    '''

    def __init__(self):
        pass
