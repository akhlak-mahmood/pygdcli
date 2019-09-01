import os
from . import log, auth, filelist, utils

log.set_max_level(log.DEBUG)

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

def execute(pwd, args):
    log.trace("Processing arguments %s" % " ".join(args))
    check_valid_command(args)

    if not 'scopes' in settings:
        settings.scopes = ['https://www.googleapis.com/auth/drive.metadata.readonly']
        settings.save(conf.settings_file)

    auth.set_scopes(settings.scopes)
    auth.authenticate()

    list_latest()
