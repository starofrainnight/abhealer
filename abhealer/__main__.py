# -*- coding: utf-8 -*-

import os
import os.path
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
import gzip
import stat
import pwd
import grp
import copy
from .pathutils import (
    get_path_owner,
    get_path_group,
    chown,
    compute_related_path,
)
from whichcraft import which


class UserData(object):
    def __init__(self):
        pass


# WARNING! When using zip compress (file_compression=True), we got this error
# when checking:
#
# java.lang.IllegalArgumentException: Cannot open an OutputStream in 'append'
# mode on a compressed FileSystem.


def get_project_template():
    from jinja2 import Environment, PackageLoader

    loader = PackageLoader("abhealer", "templates")

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


def find_data_dirs(proj_dir):
    data_dirs = []
    proj_dir = os.path.realpath(str(proj_dir))
    for afolder in os.listdir(proj_dir):
        if afolder.endswith("_data"):
            continue

        if afolder.lower() == "history":
            continue

        data_dirs.append(afolder)

    data_dirs = sorted(data_dirs, key=lambda x: folder_to_int(x))
    data_dirs = [(adir + "_data") for adir in data_dirs]

    return data_dirs


def get_trace_infos(proj_dir):
    data_dirs = find_data_dirs(proj_dir)

    trace_infos = dict()
    for adir in data_dirs:
        info_zip_path = os.path.join(str(proj_dir), adir, "trace")
        with zipfile.ZipFile(info_zip_path) as info_zip_file:
            trace_file = io.BytesIO(info_zip_file.read("trace"))

        with gzip.GzipFile(fileobj=trace_file) as trace_zip_file:
            trace_info = trace_zip_file.read().decode()

        # Parse trace info
        lines = trace_info.splitlines()
        for aline in lines:
            aline = aline.strip()
            if not aline:
                continue

            if aline.startswith("#"):
                continue

            infos = aline.split(";")
            trace_infos[infos[0]] = infos

    return trace_infos


def recover_dirs(is_dockerized, orig_dir, source_dir, dest_dir):

    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))

    if is_dockerized:
        client_source_dir = "/opt/source"
    else:
        client_source_dir = orig_dir

    trace_infos = get_trace_infos(dest_dir)

    for k, v in trace_infos.items():
        # Only process directories
        if not k.startswith("d") and not k.startswith("s"):
            continue

        source_path = pathlib.Path(source_dir) / k[1:]
        client_source_path = pathlib.Path(client_source_dir) / k[1:]

        if k.startswith("d"):
            mode_index = 2
            owner_index = 3
            group_index = 4
        elif k.startswith("s"):
            mode_index = 3
            owner_index = 4
            group_index = 5

        required_mode = int(v[mode_index]) & 0o777

        if k.startswith("d"):

            if source_path.exists():
                if (source_path.stat()[stat.ST_MODE] & 0o777) != required_mode:
                    source_path.chmod(required_mode)
            else:
                source_path.mkdir(mode=required_mode)

        elif k.startswith("s"):
            client_link_path = v[1][1:]

            if client_link_path.startswith(client_source_dir):
                source_path.unlink()
                target = compute_related_path(
                    client_source_path, client_link_path
                )
                source_path.symlink_to(target)
            else:
                source_path.unlink()
                source_path.symlink_to(client_link_path)

        if (get_path_owner(source_path) != v[owner_index]) or (
            get_path_group(source_path) != v[group_index]
        ):
            chown(
                str(source_path),
                pwd.getpwnam(v[owner_index]).pw_uid,
                grp.getgrnam(v[group_index]).gr_gid,
            )

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


def exec_(is_backup, is_dockerized, vars):
    vars = copy.deepcopy(vars)

    temp_dir = tempfile.TemporaryDirectory(prefix="abhealer")

    template = get_project_template()

    source_dir = str(vars["src_path"])

    # Get the parent dir and join with config file base name, don't use
    # specificed dest name
    dest_dir = pathlib.Path(vars["repository"]) / vars["project_name"]

    # If dest dir not existed, we must create it.
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True)

    if not is_backup:
        if not os.path.exists(source_dir):
            os.makedirs(source_dir, exist_ok=True)

        if os.listdir(source_dir):
            raise click.UsageError("Destination must be empty directory!")

    if is_dockerized:
        source_client_dir = "/opt/source"
        dest_client_dir = "/opt/backup"
        workspace_client_dir = "/opt/workspace"
    else:
        source_client_dir = os.path.abspath(source_dir)
        dest_client_dir = os.path.abspath(str(dest_dir))
        workspace_client_dir = os.path.abspath(temp_dir.name)

    fixed_config_file_name = vars["project_name"] + ".bcfg"
    fixed_config_file_path = os.path.join(
        temp_dir.name, fixed_config_file_name
    )
    # fixed_config_file_client_path = os.path.join(
    #     workspace_client_dir, fixed_config_file_name
    # )

    # Change paths
    vars["src_path"] = source_client_dir
    vars["dst_path"] = dest_client_dir

    docker_image = "starofrainnight/areca-backup"

    # To fix areca won't detect delete changes only
    areca_empty_file_path = os.path.join(source_dir, ".areca-empty")
    pathlib.Path(areca_empty_file_path).touch()

    backup_script_file_name = "_backup.sh"
    backup_script_file_path = os.path.join(
        temp_dir.name, backup_script_file_name
    )

    config_file_client_path = os.path.join(
        workspace_client_dir, fixed_config_file_name
    )
    backup_script_file_client_path = os.path.join(
        workspace_client_dir, backup_script_file_name
    )

    with temp_dir:
        if is_dockerized:
            areca_cl_script_dir = "/usr/local/bin"
        else:
            areca_cl_script_dir = which("areca_cl.sh")
            areca_cl_script_dir = os.path.dirname(areca_cl_script_dir)

        with open(backup_script_file_path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("cd %s\n" % areca_cl_script_dir)
            if is_backup:
                f.write(
                    "./areca_cl.sh backup -config %s -wdir %s\n"
                    % (config_file_client_path, workspace_client_dir)
                )
            else:
                f.write(
                    "./areca_cl.sh recover "
                    "-config %s -destination %s -o -nosubdir\n"
                    % (config_file_client_path, source_client_dir)
                )
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

        if is_dockerized:
            volume_options = ""
            # Map users and groups
            volume_options += " -v /etc/passwd:/etc/passwd "
            volume_options += " -v /etc/group:/etc/group "
            volume_options += " -v %s:%s " % (
                os.path.abspath(temp_dir.name),
                workspace_client_dir,
            )
            volume_options += " -v %s:%s " % (
                os.path.abspath(source_dir),
                source_client_dir,
            )
            volume_options += " -v %s:%s " % (
                dest_dir.resolve(),
                dest_client_dir,
            )

            backup_cmd = "docker run -t --rm %s %s %s" % (
                volume_options,
                docker_image,
                run_client_cmd,
            )
        else:
            backup_cmd = run_client_cmd

        clear_dirs(dest_dir)

        print("Executing : %s" % backup_cmd)

        os.system(backup_cmd)

        if not is_backup:
            recover_dirs(
                is_dockerized, vars["orig_path"], source_dir, dest_dir
            )

        # Don't remove empty dirs, they are valid either !
        clear_dirs(dest_dir)

    return 0


@click.group()
@click.option(
    "-m",
    "--mode",
    type=click.Choice(["auto", "local", "docker"]),
    help="""How we search areca_cl.sh, if mode=auto we will search in path and \
use docker version if mode=docker.""",
    default="auto",
)
@click.pass_context
def main(ctx, mode):
    """
    This program is a helper for dockerred Areca Backup.

    """

    """
    Areca Backup won't record the empty directories and their properties
    """

    ctx.obj = UserData()

    if mode == "auto":
        areca_cl_path = which("areca_cl.sh")
        ctx.obj.is_dockerized = areca_cl_path is None

        if areca_cl_path is None:
            click.echo(
                "Can't found areca console script, use dockerized areca ..."
            )
        else:
            click.echo("Found areca at : %s" % areca_cl_path)
    else:
        ctx.obj.is_dockerized = mode == "docker"


@main.command()
@click.argument("config", type=click.File())
@click.pass_context
def backup(ctx, config):
    """
    Backup a series projects to repository.

    Project and repository paths are defined in config file.

    \b
    CONFIG: The config file (in YAML format) path.
    """

    vars = yaml.load(config)
    for source in vars["sources"]:
        # Support path only source
        if isinstance(source, six.string_types):
            source = [source]

        vars["src_path"] = source[0]
        vars["project_name"] = os.path.splitext(os.path.basename(source[0]))[0]
        if (len(source) > 1) and (len(source[1].strip()) > 0):
            vars["project_name"] = source[1].strip()

        ret = exec_(True, ctx.obj.is_dockerized, vars)
        if ret:
            return ret

    return 0


@main.group()
@click.pass_context
def recover(ctx):
    """
    Recover projects from backup repository.
    """
    pass


@recover.command()
@click.argument("config", type=click.File())
@click.argument("name")
@click.argument("to_path")
@click.pass_context
def proj(ctx, config, name, to_path):
    """
    Only recover specific project

    \b
    CONFIG  : The config file (in YAML format) path
    NAME    : Project name
    TO_PATH : Where you store the recovered project
    """

    vars = yaml.load(config)

    for source in vars["sources"]:
        # Support path only source
        if isinstance(source, six.string_types):
            source = [source]

        vars["project_name"] = os.path.splitext(os.path.basename(source[0]))[0]

        if (len(source) > 1) and (len(source[1].strip()) > 0):
            vars["project_name"] = source[1].strip()

        click.echo("%s to %s" % (vars["project_name"], name))
        if vars["project_name"] != name:
            continue

        vars["src_path"] = to_path
        vars["orig_path"] = os.path.realpath(os.path.normpath(source[0]))

        ret = exec_(False, ctx.obj.is_dockerized, vars)
        if ret:
            return ret

        # Only exactly one project with spectific name.
        return 0

    # If no project founded, we should raise error
    raise click.BadArgumentUsage('Project "%s" not found!' % name)


@recover.command()
@click.argument("config", type=click.File())
@click.argument("to_path")
@click.pass_context
def repo(ctx, config, to_path):
    """
    Recover whole repository

    \b
    CONFIG  : The config file (in YAML format) path
    TO_PATH : Where you store the recovered project
    """

    vars = yaml.load(config)
    for source in vars["sources"]:
        # Support path only source
        if isinstance(source, six.string_types):
            source = [source]

        vars["project_name"] = os.path.splitext(os.path.basename(source[0]))[0]

        if (len(source) > 1) and (len(source[1].strip()) > 0):
            vars["project_name"] = source[1].strip()

        vars["src_path"] = os.path.join(to_path, vars["project_name"])

        vars["orig_path"] = os.path.realpath(os.path.normpath(source[0]))

        if exec_(False, ctx.obj.is_dockerized, vars):
            break

    return 0


if __name__ == "__main__":
    # execute only if run as a script
    main()
