# -*- coding: utf-8 -*-

import sys
import os.path
import pwd
import grp
import pathlib


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


def normal_path(apath):
    apath = os.path.abspath(str(apath))
    if sys.platform == "win32":
        apath = apath.replace("/", "\\")
    else:
        apath = apath.replace("\\", "/")
    return pathlib.Path(apath)


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
            "../" * (len(link.parents) - found_index), target.name
        )
    elif found_index == max_parents:
        return target.name
    else:
        # Don't join like this:
        #
        #    os.path.join(*target_parents[found_index:], target.name)
        #
        # This syntax will lead python below v3.4 report error : "SyntaxError:
        # only named arguments may follow *expression"!
        return os.path.join(
            os.path.join(*target_parents[found_index:]), target.name
        )
