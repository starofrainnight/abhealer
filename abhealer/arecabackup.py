# -*- coding: utf-8 -*-

"""
This module contained a series classes that use for maintain informations of
Areca Backup.
"""

import arrow
import zipfile
import gzip
import io
import os
import os.path
import subprocess
import xml.etree.ElementTree as etree
from whichcraft import which
from pathlib import Path
from . import abhealer, pathutils


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


class TraceInfo(object):
    def __init__(self, info):
        self._parties = info.split(";")

        atype = self.type_

        if atype == "f":
            mode_index = 4
            owner_index = 5
            group_index = 6
        elif atype == "d":
            mode_index = 2
            owner_index = 3
            group_index = 4
        elif atype == "s":
            mode_index = 3
            owner_index = 4
            group_index = 5

        self._mode = int(self._parties[mode_index])
        self._owner = self._parties[owner_index]
        self._group = self._parties[group_index]

    @property
    def type_(self):
        return self._parties[0][0]

    @property
    def path(self):
        return self._parties[0][1:]

    @property
    def mode(self):
        return self._mode

    @property
    def owner(self):
        return self._owner

    @property
    def group(self):
        return self._group

    def __repr__(self):
        return '%s("%s", "%s")' % (
            type(self).__qualname__,
            self.type_,
            self.path,
        )


class DataInfo(object):
    DIR_SUFFIX = "_data"

    def __init__(self, adir):
        self._base_dir = adir

    def _extract_data(self, name):
        info_zip_path = self.base_dir / name
        with zipfile.ZipFile(str(info_zip_path)) as info_zip_file:
            data_file = io.BytesIO(info_zip_file.read(name))

        with gzip.GzipFile(fileobj=data_file) as data_zip_file:
            data = data_zip_file.read().decode()

        return data

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

    @property
    def traces(self):
        infos = list()

        data = self._extract_data("trace")

        # Parse trace info
        lines = data.splitlines()
        for aline in lines:
            aline = aline.strip()
            if not aline:
                continue

            if aline.startswith("#"):
                continue

            info = TraceInfo(aline)
            infos.append(info)

        return infos

    @property
    def manifest(self):
        """
        Get manifest of this backup data info.

        Return a root element of ElementTree about the xml content.

        Sample manifest content:

        <?xml version="1.0" encoding="UTF-8"?>
        <manifest version="1" type="0" date="2017_11_03 20h56-38-284">
        <properties>
        <property key="Archive name" value="201711032056" />
        <property key="Archive size" value="256" />
        <property key="Areca Home" value="/home/useradmin/applications/areca/bin" />
        <property key="Backup duration" value="273 ms" />
        <property key="Build id" value="5872222636083894532" />
        <property key="Checked" value="false" />
        <property key="File encoding" value="UTF-8" />
        <property key="Filtered entries" value="0" />
        <property key="JRE" value="/usr/lib/jvm/java-8-openjdk-amd64/jre" />
        <property key="Operating system" value="Linux - 4.4.0-34-generic" />
        <property key="Option [backup scheme]" value="Incremental backup" />
        <property key="Scanned entries (files or directories)" value="2" />
        <property key="Source path" value="/mnt/data/sources/projects/abhealer/from" />
        <property key="Stored files" value="1" />
        <property key="Target ID" value="from" />
        <property key="Unfiltered directories" value="1" />
        <property key="Unfiltered files" value="1" />
        <property key="Unmodified files (not stored)" value="0" />
        <property key="Version" value="7.5" />
        <property key="Version date" value="August 26, 2015" />
        </properties>
        </manifest>
        """  # noqa

        data = self._extract_data("manifest")
        return etree.fromstring(data)

    def _name_without_suffix(self):
        return self.base_dir.name[: -len(self.DIR_SUFFIX)]

    def __repr__(self):
        return "%s(%s)" % (type(self).__qualname__, int(self))

    def __int__(self):
        return folder_to_int(self._name_without_suffix())


class Project(object):
    def __init__(self, repository, cfg, adir):
        self._base_dir = Path(adir)
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
        return '%s("%s")' % (type(self).__qualname__, self.name)


class Repository(object):
    CFG_DIR_NAME = "areca_config_backup"

    def __init__(self, adir):
        self._base_dir = Path(adir)

        # Validate directory
        self._cfg_dir = self._base_dir / self.CFG_DIR_NAME
        if not self._cfg_dir.exists():
            msg = (
                "'%s' directory not found ! The directory "
                "is not an Areca Backup repository: %s!"
            )
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

        all = []
        for subdir in self.base_dir.iterdir():
            if subdir.name == self.CFG_DIR_NAME:
                continue

            history_path = subdir / "history"
            if (not history_path.exists()) or (not history_path.is_file()):
                abhealer.logger().warn(
                    "Found invalid project : %s" % subdir.name
                )
                continue

            cfg_path = self.cfg_dir / (subdir.name + ".bcfg")
            all.append(Project(self, etree.parse(str(cfg_path)), subdir))

        return all


class LocalArecaBackup(object):
    """
    The class use for maintain Areca Backup's behaviors.
    """

    def __init__(self):
        # Search areca backup script in PATH
        self._program_path = self._detect_program_path()

    def _detect_program_path(self):
        apath = which("areca_cl.sh")
        if apath is None:
            return None

        return Path(apath)

    def backup(self, cfg_path, ws_dir):
        return subprocess.call(
            self.gen_backup_cmd(cfg_path, ws_dir), shell=True
        )

    def recover(self, cfg_path, dst_dir):
        return subprocess.call(
            self.gen_recover_cmd(cfg_path, dst_dir), shell=True
        )

    def gen_backup_cmd(self, cfg_path, ws_dir=None):
        """
        Generate backup command

        :param ws_dir: Working directory during archive check. Default to None
        for use cfg_path's path
        """
        cfg_path = pathutils.normal_path(cfg_path)

        if ws_dir:
            ws_dir = pathutils.normal_path(ws_dir)
        else:
            ws_dir = pathutils.normal_path(cfg_path).parent

        cmd = "cd %s; ./areca_cl.sh backup -config %s -wdir %s"
        cmd = cmd % (self._program_path.parent, str(cfg_path), str(ws_dir))
        return cmd

    def gen_recover_cmd(self, cfg_path, dst_dir):

        cfg_path = pathutils.normal_path(cfg_path)
        dst_dir = pathutils.normal_path(dst_dir)

        cmd = (
            "cd %s; ./areca_cl.sh recover -config %s -destination %s "
            "-o -nosubdir"
        )
        cmd = cmd % (self._program_path.parent, str(cfg_path), str(dst_dir))

        return cmd


class DockerizedArecaBackup(LocalArecaBackup):
    """
    The class use for maintain Dockerized Areca Backup's behaviors.
    """

    CMD_PREFIX = "docker run -t --rm starofrainnight/areca-backup "
    SRC_DIR = "/opt/source"
    DST_DIR = "/opt/backup"
    WS_DIR = "/opt/workspace"
    CFG_DIR = "/opt/config"

    def __init__(self):
        super().__init__()

    def _detect_program_path(self):
        cmd = "%s bash --version" % self.CMD_PREFIX
        ret = subprocess.call(cmd, shell=True)
        if ret:
            return None

        return Path("/usr/local/bin/areca_cl.sh")

    def gen_docker_volume_options(self, cfg_path, dst_dir):
        pass

    def gen_backup_cmd(self, cfg_path, ws_dir=None):
        cfg_path = pathutils.normal_path(cfg_path)
        client_cfg_path = os.path.join(self.CFG_DIR, cfg_path.name)

        if ws_dir:
            ws_dir = pathutils.normal_path(ws_dir)
        else:
            ws_dir = pathutils.normal_path(cfg_path).parent

        cmd = super().gen_backup_cmd(client_cfg_path, self.WS_DIR)

        return cmd

    def gen_recover_cmd(self, cfg_path, dst_dir):
        cfg_path = pathutils.normal_path(cfg_path)
        client_cfg_path = os.path.join(self.CFG_DIR, cfg_path.name)

        dst_dir = pathutils.normal_path(dst_dir)

        cmd = super().gen_recover_cmd(client_cfg_path, self.DST_DIR)

        return cmd
