from . import log

log.set_max_level(log.DEBUG)

def handle_command(args):
    log.trace("Processing arguments %s" % " ".join(args))

