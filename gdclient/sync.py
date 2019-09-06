import os

from . import log 
from . import auth
from . import database as db 

from .errors import *
from .filesystem import FileSystem
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

class Sync:
    def __init__(self, scopes, credentials_file, token_file):
        self.scopes = scopes
        self.credentials_file = credentials_file
        self.token_file = token_file

        self.setup_auth()
        self.login()

        self.queue = []

    def setup_auth(self):
        auth.set_scopes(self.scopes)

    def login(self):
        auth.authenticate(self.credentials_file, self.token_file)

    def __repr__(self):
        return "SyncQ items: \n" + "\n".join([str(i) for i in self.queue])

    def add(self, item):
        """ Add an item to sync queue """
        if not isinstance(item, FileSystem):
            raise ErrorNotFileSystemObject(item)

        if not db.file_exists(item):
            # items added to the queue need to be added to 
            # the database first.
            # @todo: remove this check once everything is OK to avoid performance issues
            raise FileNotFoundError("Not in database: ", item)

        self.queue.append(item)
        log.trace("SyncQ (add): ", item)

    def _process_item(self, item):
        log.say("Checking item: ", item)

        try:
            mirror = db.get_mirror(item)
        except ErrorParentNotFound:
            log.warn("No mirror parent directory exists in database. Might be a untracked item.", item)
            return False

        # if it's a directory
        # for each item, check if there is a mirror item exists in db
        # if yes, update status to syncd
        # else, create/update the mirror item
        if item.is_dir():
            if db.mirror_exists(item):
                log.trace("Mirror directory exists in database. ", item)
                log.trace("Sync OK:", item)
            else:
                mirror.create_dir()
                db.add(mirror)
        else:
            if db.mirror_exists(item):
                if not item.same_file(mirror):
                    self._sync_file(item, mirror)
                else:
                    log.say("No change: ", item.path)
            else:
                mirror = item.upload_or_download(mirror)
                db.add(mirror)

        db.update_status(item, db.Status.synced)
        db.update_status(mirror, db.Status.synced)

    def run(self):
        """ Process sync queue """
        log.say("Running SyncQ")

        while self.queue:
            self._process_item(self.queue.pop(0))

        log.say("Finish SyncQ")

    def _sync_file(self, item, mirror):
        """ Sync the item with it's mirror file. 
            Do extensive checking to modified time to determine sync direction.
            If modification detected in both local and remote, abort syncing. """

        log.trace("Checking sync direction, not implemented")
