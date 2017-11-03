# -*- coding: utf-8 -*-

'''
This module contained a series classes that use for maintain informations of
Areca Backup.
'''

import pathlib


class Project(object):

    def __init__(self, adir):
        self._dir = pathlib.Path(adir)

    @property
    def dir_(self):
        return self._dir


class Repository(object):

    def __init__(self, adir):
        self._dir = pathlib.Path(adir)

        # Validate directory
        cfg_backup_dir = self.dir_ / "areca_config_backup"
        if not cfg_backup_dir.exist():
            msg = ("The directory is not an Areca Backup repository "
                   "directory: %s!")
            msg = msg % self.dir_
            raise NotADirectoryError(msg)

    @property
    def dir_(self):
        return self._dir


class ArecaBackup(object):
    '''
    The class use for maintain Areca Backup's behaviors.
    '''

    def __init__(self):
        pass
