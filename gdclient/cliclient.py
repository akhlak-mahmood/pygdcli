from . import log
from . import auth

log.set_max_level(log.DEBUG)

def check_valid_command(args):
    pass

def handle_command(args):
    log.trace("Processing arguments %s" % " ".join(args))
    check_valid_command(args)

    auth.set_scopes(['https://www.googleapis.com/auth/drive.metadata.readonly'])
    auth.authenticate()

