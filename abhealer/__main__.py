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
import stat


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


def get_dirs_record_path(dest_dir):
    dest_dir = pathlib.Path(dest_dir)

    folder = find_latest_dir(dest_dir)

    apath = dest_dir / folder
    apath = pathlib.Path(str(apath) + "_data")
    apath = apath / "dir_stats.yaml"

    return apath


def backup_dirs(source_dir, dest_dir):
    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))

    record_path = get_dirs_record_path(dest_dir)
    if record_path.exists():
        raise click.UsageError("Directories list file exists : %s" %
                               record_path)

    dir_infos = []

    print("Generating directories list : %s" % record_path)
    for root, dirs, files in os.walk(source_dir):
        for adir in dirs:
            apath = os.path.join(root, adir)
            apath = os.path.realpath(apath)

            shorten_path = apath[len(source_dir) + 1:]

            apath_object = pathlib.Path(apath)

            dir_infos.append({
                "path": shorten_path,
                'mode': os.stat(apath)[stat.ST_MODE] & 0o777,
                'user': apath_object.owner(),
                'group': apath_object.group(),
            })

    with record_path.open("w") as f:
        yaml.dump(dir_infos, f)

    print("Finished generate directories list")


def recover_dirs(source_dir, dest_dir):
    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))

    record_path = get_dirs_record_path(dest_dir)
    if not record_path.exists():
        raise click.UsageError(
            "Dirs file not exists : %s" % record_path)

    with record_path.open() as f:
        dir_infos = yaml.load(f)

    for dir_info in dir_infos:
        full_path = os.path.join(source_dir, dir_info["path"])
        full_path = pathlib.Path(full_path)

        if not full_path.exists():
            full_path.mkdir(mode=dir_info["mode"])
        else:
            full_path.chmod(dir_info["mode"])

    print("Recover directories permissions completed!")


def clear_dirs(dest_dir):
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


def exec_(is_backup, vars):
    temp_dir = tempfile.TemporaryDirectory(prefix="dockerred_areca")

    template = get_project_template()

    source_dir = vars["src_path"]
    source_client_dir = "/opt/source"

    # Get the parent dir and join with config file base name, don't use
    # specificed dest name
    dest_dir = pathlib.Path(vars["dst_path"])

    # If dest dir not existed, we must not do any action!
    if not dest_dir.exists():
        raise click.UsageError('Directory not existed : "%s" !' % dest_dir)

    if not is_backup:
        if os.listdir(str(source_dir)):
            raise click.UsageError(
                "Destination must be empty directory!")

    dest_client_dir = "/opt/backup"
    workspace_client_dir = "/opt/workspace"

    fixed_config_file_name = vars["project_name"] + ".bcfg"
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
        # Map users and groups
        volume_options += " -v /etc/passwd:/etc/passwd "
        volume_options += " -v /etc/group:/etc/group "
        volume_options += " -v %s:%s " % (
            os.path.abspath(temp_dir.name), workspace_client_dir)
        volume_options += " -v %s:%s " % (
            os.path.abspath(source_dir), source_client_dir)
        volume_options += " -v %s:%s " % (
            dest_dir.resolve(), dest_client_dir)

        clear_dirs(dest_dir)

        backup_cmd = "docker run -t --rm %s %s %s" % (
            volume_options, docker_image, run_client_cmd)
        print("Executing : %s" % backup_cmd)

        os.system(backup_cmd)

        if is_backup:
            backup_dirs(source_dir, dest_dir)
        else:
            recover_dirs(source_dir, dest_dir)

        # Don't remove empty dirs, they are valid either !
        clear_dirs(dest_dir)

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
def backup(**kwargs):
    """
    """

    config_file_name = os.path.basename(kwargs["config"].name)
    vars = yaml.load(kwargs["config"])
    vars["project_name"] = os.path.splitext(config_file_name)[0]

    return exec_(True, vars)


@main.command()
@click.option('-c', '--config', required=True, type=click.File())
@click.option('-t', '--to-path', help="Recover to path, default to src_path")
def recover(**kwargs):
    """
    """

    config_file_name = os.path.basename(kwargs["config"].name)
    vars = yaml.load(kwargs["config"])
    if kwargs["to_path"]:
        vars["src_path"] = kwargs["to_path"]

    vars["project_name"] = os.path.splitext(config_file_name)[0]

    return exec_(False, vars)

if __name__ == "__main__":
    # execute only if run as a script
    main()
