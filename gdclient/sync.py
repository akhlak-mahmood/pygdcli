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

        self._queue = []
        self._upload_or_download_queue = []
        self._update_queue = []

    def setup_auth(self):
        auth.set_scopes(self.scopes)

    def login(self):
        auth.authenticate(self.credentials_file, self.token_file)

    def __repr__(self):
        return  "SyncQ items: \n" + "\n".join([str(i) for i in self._queue]) \
            +   "Load items: \n" + "\n".join([str(i) for i in self._upload_or_download_queue]) \
            +   "Update items: \n" + "\n".join([str(i) for i in self._update_queue])

    def add(self, item):
        """ Add an item to sync queue """
        if not isinstance(item, FileSystem):
            raise ErrorNotFileSystemObject(item)

        # if type and path not in queue
        if not any(x for x in self._queue if all([x.path == item.path, x.__class__ == item.__class__])):
            self._queue.append(item)
            log.trace("SyncQ (add): ", item)

    def _process_item(self, item):
        log.say("Checking item: ", item)

        try:
            # this will resolve if the path is within
            # local or remote root
            mirror = db.get_mirror(item)
        except ErrorParentNotFound:
            log.warn("No mirror parent directory exists in database. Might be an untracked item.", item)
            return False

        # if it's a directory
        # check if there is a mirror item exists in db
        # if yes, update status to syncd
        # else, create the mirror directory
        if item.is_dir():
            if db.file_exists(item):
                log.trace("Directory exists in database. All OK.", item)
            else:
                log.trace("Adding new directory", item)
                db.add(item)
                if db.mirror_exists(item):
                    log.trace("Mirror directory exists in database. ", item)
                    log.trace("Sync OK:", item)
                else:
                    mirror.create_dir()
                    db.add(mirror)
        else:
            # database contains all the syncd items
            # check if current file props matches with the saved props
            if db.file_exists(item):
                # get the file info as saved in database
                dbFile = db.get_file_as_db(item)

                # check if file props are still same
                if not item.same_file(dbFile):
                    log.trace("Change found", item)
                    # if already a mirror, sync them
                    if db.mirror_exists(item) and not item.same_file(mirror):
                        self._update_queue.append((item, mirror))
                    else:
                        log.trace("Downloading/Uploading mirror file", item)
                        self._upload_or_download_queue.append((item,mirror))
                        # mirror = item.upload_or_download(mirror)
                        # db.add(mirror)
                else:
                    # if no change at all or if a new file
                    log.trace("No change found", item)
            else:
                log.trace("New file: ", item)
                db.add(item)
                if db.mirror_exists(item):
                    if not item.same_file(mirror):
                        self._update_queue.append((item, mirror))
                    else:
                        log.say("No change: ", item.path)
                else:
                    log.trace("Downloading/Uploading mirror file", item)
                    self._upload_or_download_queue.append((item,mirror))
                    # mirror = item.upload_or_download(mirror)
                    # db.add(mirror)

        db.update_status(item, db.Status.synced)
        db.update_status(mirror, db.Status.synced)

    def run(self):
        """ Process sync queue """
        log.say("Running SyncQ: ", len(self._queue), "items")

        while self._queue:
            self._process_item(self._queue.pop(0))

        log.say("Finish SyncQ")

    def _sync_file(self, item, mirror):
        """ Sync the item with it's mirror file. 
            Do extensive checking to modified time to determine sync direction.
            If modification detected in both local and remote, abort syncing. """
        log.trace("Syncing", item, " and ", mirror)
        log.trace("Checking sync direction, not implemented")

        iModified = item.modifiedTime()
        mModified = mirror.modifiedTime()

