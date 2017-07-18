# -*- coding: utf-8 -*-

import os
import os.path
import sys
import click
import six
import io
import tempfile
import pathlib
import glob
import shutil
import fnmatch
import yaml


# WARNING! When using zip compress (file_compression=True), we got this error
# when checking:
#
# java.lang.IllegalArgumentException: Cannot open an OutputStream in 'append'
# mode on a compressed FileSystem.

def get_project_template():
    from jinja2 import Environment, PackageLoader

    loader = PackageLoader('abhealer', 'templates')

    env = Environment(loader=loader)

    return env.get_template("project.bcfg")


def clear_empty_dirs(dest_dir):
    # Clear empty backups that only have
    dirs = glob.glob(os.path.join(str(dest_dir), "*"))
    for adir in dirs:
        if not os.path.isdir(adir):
            continue

        adir = pathlib.Path(adir)
        data_dir = adir.parent / (adir.stem + "_data" + adir.suffix)

        if fnmatch.fnmatch(adir.stem, "*_data"):
            continue

        if not data_dir.exists():
            print("Removed damaged empty backup directory : %s" % adir)
            shutil.rmtree(str(adir), ignore_errors=True)
            continue

        # files = os.listdir(str(adir))

        # There only have .areca-empty file !

        # We must not remove the version that only have .areca-empty changes,
        # otherwise we can't restore the files.

        # Until we find out what's make this not working, MUST not enable
        # codes below:

        # if len(files) <= 1:
        #     # Removed *_data directory first, so we know if a directory
        #     # successed be removed last time.
        #     print("Removing empty backup directory : %s" % adir)
        #     shutil.rmtree(str(data_dir), ignore_errors=True)
        #     shutil.rmtree(str(adir), ignore_errors=True)


def exec_(is_backup, config):
    config_file_path = config.name

    temp_dir = tempfile.TemporaryDirectory(prefix="dockerred_areca")
    config_file_name = os.path.basename(config_file_path)
    config_file_name_without_ext = os.path.splitext(config_file_name)[0]

    template = get_project_template()
    vars = yaml.load(config)

    vars["project_name"] = config_file_name_without_ext

    source_dir = vars["src_path"]
    source_client_dir = "/opt/source"

    # Get the parent dir and join with config file base name, don't use
    # specificed dest name
    dest_dir = pathlib.Path(vars["dst_path"]).parents[0]
    dest_dir = dest_dir / config_file_name_without_ext

    # If dest dir not existed, we must not do any action!
    if not dest_dir.exists():
        raise OSError('Directory not existed : "%s" !' % dest_dir)

    dest_client_dir = "/opt/backup"
    workspace_client_dir = "/opt/workspace"

    fixed_config_file_name = config_file_name_without_ext + ".bcfg"
    fixed_config_file_path = os.path.join(
        temp_dir.name, fixed_config_file_name)
    fixed_config_file_client_path = os.path.join(
        workspace_client_dir, fixed_config_file_name)

    # Change paths
    vars["src_path"] = source_client_dir
    vars["dst_path"] = dest_client_dir

    docker_image = "starofrainnight/areca-backup"

    # To fix areca won't detect delete changes only
    areca_empty_file_path = os.path.join(source_dir, ".areca-empty")
    pathlib.Path(areca_empty_file_path).touch()

    backup_script_file_name = "_backup.sh"
    backup_script_file_path = os.path.join(
        temp_dir.name, backup_script_file_name)

    config_file_client_path = os.path.join(
        workspace_client_dir, fixed_config_file_name)
    backup_script_file_client_path = os.path.join(
        workspace_client_dir, backup_script_file_name)

    with temp_dir:
        with open(backup_script_file_path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("cd /usr/local/bin\n")
            if is_backup:
                f.write("./areca_cl.sh backup -config %s -wdir %s\n" % (
                    config_file_client_path, workspace_client_dir))
            else:
                f.write("./areca_cl.sh recover "
                        "-config %s -destination %s -o -nosubdir\n" % (
                            config_file_client_path, source_client_dir))
            f.write("\n")
        os.system("chmod +x %s" % backup_script_file_path)

        print("===== script begin =====")
        with open(backup_script_file_path, "rb") as f:
            print(f.read().decode("utf-8"))
        print("===== script end =====")

        # Write fixed config file
        xml_content = template.render(vars)
        with open(fixed_config_file_path, "wb") as f:
            f.write(xml_content.encode("utf-8"))

        print("===== xml begin =====")
        print(xml_content)
        print("===== xml end =====")

        run_client_cmd = backup_script_file_client_path

        volume_options = ""
        volume_options += " -v %s:%s " % (
            os.path.abspath(temp_dir.name), workspace_client_dir)
        volume_options += " -v %s:%s " % (
            os.path.abspath(source_dir), source_client_dir)
        volume_options += " -v %s:%s " % (
            dest_dir.resolve(), dest_client_dir)

        clear_empty_dirs(dest_dir)

        backup_cmd = "docker run -t --rm %s %s %s" % (
            volume_options, docker_image, run_client_cmd)
        print("Executing : %s" % backup_cmd)

        os.system(backup_cmd)

        clear_empty_dirs(dest_dir)

    return 0


@click.group()
def main(args=None):
    """
    This program is a helper for dockerred Areca Backup.

    """

    """
    Areca Backup won't record the empty directories and their properties
    """


@main.command()
@click.option('-c', '--config', type=click.File())
def backup(config):
    """
    """

    return exec_(True, config)


@main.command()
@click.option('-c', '--config', type=click.File())
def recover(config):
    """
    """

    return exec_(False, config)

if __name__ == "__main__":
    # execute only if run as a script
    main()
