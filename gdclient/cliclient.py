import os
from . import log, auth, filelist, utils

from pprint import pprint as pp
log.set_max_level(log.DEBUG)

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# global vars
conf = utils.AttrDict({})
conf.pwd = os.getcwd()

# persistence settings
conf.settings_file = os.path.join(conf.pwd, 'settings.json')
settings = utils.AttrDict()
if os.path.isfile(conf.settings_file):
    settings.load_json(conf.settings_file)

def check_valid_command(args):
    pass

def list_latest():
    filelist.list_latest_files()

conf.current_dir = None
conf.last_result = None
conf.current_dirs = []

def handle_command(command):
    log.trace("Processing ", command)

    if command in ["ls", "list", "dir"]:
        conf.current_dirs = filelist.get_root_dirs()
        pp(conf.current_dirs)

        return True

    elif command.split()[0] in ["cd", "chdir"]:
        dirname = command.split()[1]
        dirobj = None
        for d in conf.current_dirs:
            if dirname == d["name"]:
                dirobj = d 

        if dirobj:
            conf.last_result = filelist.change_directory(dirobj)
            conf.current_dir = dirobj
            pp(conf.last_result)
        else:
            log.warn("Unknown directory name ", dirname)

        return True

    elif command.split()[0] in ["get", "download"]:
        fileid = int(command.split()[1])
        fileobj = conf.last_result['files'][fileid]
        filelist.download_file(fileobj)
        return True

    elif command.split()[0] in ["put", "upload"]:
        conf.last_result = filelist.upload_file("/home/akhlak/Pictures/cost-function.png")
        pp(conf.last_result)
        return True

    return False

def execute(pwd, args):
    log.trace("Processing arguments %s" % " ".join(args))
    check_valid_command(args)
    auth.set_scopes(settings.scopes)
    auth.authenticate()
    utils.interactive(handle_command)
