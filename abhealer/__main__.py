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
import zipfile


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


def find_latest_dir(dest_dir):
    # Find the latest dir
    max_value = 0
    dest_dir = os.path.realpath(str(dest_dir))
    for afolder in os.listdir(dest_dir):
        if afolder.endswith("_data"):
            continue

        if afolder.lower() == "history":
            continue

        value = folder_to_int(afolder)
        if value > max_value:
            max_value = value

    if max_value <= 0:
        return

    return int_to_folder(max_value)


def backup_empty_dirs(source_dir, dest_dir):
    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))
    folder = find_latest_dir(dest_dir)

    empty_dirs_zip_path = os.path.join(dest_dir, folder)
    empty_dirs_zip_path = empty_dirs_zip_path + "_data"
    empty_dirs_zip_path = os.path.join(empty_dirs_zip_path, "empty-dirs.zip")
    if os.path.exists(empty_dirs_zip_path):
        print("WARNING: File exists : %s" % empty_dirs_zip_path)
        return

    old_cwd = os.getcwd()
    try:
        os.chdir(source_dir)

        print("Generating empty directories list : %s" % empty_dirs_zip_path)
        for root, dirs, files in os.walk("."):
            for adir in dirs:
                apath = os.path.join(root, adir)
                if os.listdir(apath):
                    continue

                # FIXME: It won't record the user name belongs to.
                os.system("zip -0 -y -v %s %s" % (empty_dirs_zip_path, apath))

        print("Finished generate empty directories list")
    finally:
        os.chdir(old_cwd)


def recover_empty_dirs(source_dir, dest_dir):
    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))
    folder = find_latest_dir(dest_dir)

    empty_dirs_zip_path = os.path.join(dest_dir, folder)
    empty_dirs_zip_path = empty_dirs_zip_path + "_data"
    empty_dirs_zip_path = os.path.join(empty_dirs_zip_path, "empty-dirs.zip")
    if not os.path.exists(empty_dirs_zip_path):
        print("WARNING: File not exists : %s" % empty_dirs_zip_path)
        return

    os.system("unzip -v -d %s %s" % (source_dir, empty_dirs_zip_path))


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
    dest_dir = pathlib.Path(vars["dst_path"])

    # If dest dir not existed, we must not do any action!
    if not dest_dir.exists():
        raise OSError('Directory not existed : "%s" !' % dest_dir)

    if not is_backup:
        if dest_dir.glob("*"):
            raise click.UsageError(
                "Destination must be empty directory!")

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

        if is_backup:
            backup_empty_dirs(source_dir, dest_dir)
        else:
            recover_empty_dirs(source_dir, dest_dir)

        # Don't remove empty dirs, they are valid either !
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
@click.option('-c', '--config', required=True, type=click.File())
def backup(config):
    """
    """

    return exec_(True, config)


@main.command()
@click.option('-c', '--config', required=True, type=click.File())
def recover(config):
    """
    """

    return exec_(False, config)

if __name__ == "__main__":
    # execute only if run as a script
    main()
