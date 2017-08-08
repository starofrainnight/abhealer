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
import gzip
import stat
import pwd
import grp


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


def find_data_dirs(dest_dir):
    data_dirs = []
    dest_dir = os.path.realpath(str(dest_dir))
    for afolder in os.listdir(dest_dir):
        if afolder.endswith("_data"):
            continue

        if afolder.lower() == "history":
            continue

        data_dirs.append(afolder)

    data_dirs = sorted(data_dirs, key=lambda x: folder_to_int(x))
    data_dirs = [(adir + "_data") for adir in data_dirs]

    return data_dirs


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


def get_trace_infos(dest_dir):
    data_dirs = find_data_dirs(dest_dir)

    trace_infos = dict()
    for adir in data_dirs:
        info_zip_path = os.path.join(str(dest_dir), adir, "trace")
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

            if aline.startswith('#'):
                continue

            infos = aline.split(';')
            trace_infos[infos[0]] = infos

    return trace_infos


def normal_path(apath):
    if sys.platform == 'win32':
        return os.path.abspath(apath).replace("/", "\\")
    else:
        return os.path.abspath(apath).replace("\\", "/")


def compute_related_path(link, target):
    link = pathlib.Path(normal_path(str(link)))
    target = pathlib.Path(normal_path(str(target)))

    link_parents = [str(p) for p in reversed(link.parents)]
    target_parents = [str(p) for p in reversed(target.parents)]

    max_parents = min(len(link.parents), len(target.parents))
    found_index = max_parents
    for i in range(0, max_parents):
        if link_parents[i] != target_parents[i]:
            found_index = i
            break

    if len(link.parents) > len(target.parents):
        return os.path.join(
            "../" * (len(link.parents) - found_index), target.name)
    else:
        # Don't join like this:
        #
        #    os.path.join(*target_parents[found_index:], target.name)
        #
        # This syntax will lead python below v3.4 report error : "SyntaxError:
        # only named arguments may follow *expression"!
        return os.path.join(
            os.path.join(*target_parents[found_index:]), target.name)


def get_path_owner(apath):
    apath = str(apath)
    if os.path.islink(apath):
        return pwd.getpwuid(os.lstat(apath).st_uid).pw_name
    else:
        return pwd.getpwuid(os.stat(apath).st_uid).pw_name


def get_path_group(apath):
    apath = str(apath)
    if os.path.islink(apath):
        return grp.getgrgid(os.lstat(apath).st_gid).gr_name
    else:
        return grp.getgrgid(os.stat(apath).st_gid).gr_name


def chown(apath, uid, gid):
    apath = str(apath)
    if os.path.islink(apath):
        os.lchown(apath, uid, gid)
    else:
        os.chown(apath, uid, gid)


def recover_dirs(source_dir, dest_dir):

    source_dir = os.path.realpath(str(source_dir))
    dest_dir = os.path.realpath(str(dest_dir))

    client_source_dir = "/opt/source"

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
                    client_source_path, client_link_path)
                source_path.symlink_to(target)
            else:
                source_path.unlink()
                source_path.symlink_to(client_link_path)

        if ((get_path_owner(source_path) != v[owner_index])
                or (get_path_group(source_path) != v[group_index])):
            chown(
                str(source_path),
                pwd.getpwnam(v[owner_index]).pw_uid,
                grp.getgrnam(v[group_index]).gr_gid)

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

        if not is_backup:
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
