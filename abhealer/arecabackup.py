# -*- coding: utf-8 -*-

'''
This module contained a series classes that use for maintain informations of
Areca Backup.
'''

import pathlib


class Project(object):

    def __init__(self, adir):
        self._base_dir = pathlib.Path(adir)

    @property
    def base_dir(self):
        return self._base_dir


class Repository(object):

    def __init__(self, adir):
        self._base_dir = pathlib.Path(adir)

        # Validate directory
        self._cfg_dir = self._base_dir / "areca_config_backup"
        if not self._cfg_dir.exist():
            msg = ("The directory is not an Areca Backup repository "
                   "directory: %s!")
            msg = msg % self._base_dir
            raise NotADirectoryError(msg)

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def cfg_dir(self):
        return self._cfg_dir

    @property
    def projects(self):
        pass


class ArecaBackup(object):
    '''
    The class use for maintain Areca Backup's behaviors.
    '''

    def __init__(self):
        pass
