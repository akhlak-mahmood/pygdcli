import os

from . import log 
from . import auth
from . import database as db 

from .errors import *
from .filesystem import FileSystem
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

class Task:
    create  = 1
    load    = 2
    update  = 3
    delete  = 4
    trash   = 5
    rename  = 6
    copy    = 7

class Sync:
    def __init__(self, scopes, credentials_file, token_file):
        self.scopes = scopes
        self.credentials_file = credentials_file
        self.token_file = token_file
        self._login = False

        self.setup_auth()

        self._check_queue = []
        self._sync_queue = []

    def setup_auth(self):
        auth.set_scopes(self.scopes)

    def login(self):
        if not self._login:
            auth.authenticate(self.credentials_file, self.token_file)
            self._login = True

    def __repr__(self):
        return  "SyncQ items: \n" + "\n".join([str(i) for i in self._sync_queue])
        

    def add(self, item):
        """ Add an item to sync queue """
        if not isinstance(item, FileSystem):
            raise ErrorNotFileSystemObject(item)

        # if type and path not in queue
        if not any(x for x in self._check_queue if all([x.path == item.path, x.__class__ == item.__class__])):
            self._check_queue.append(item)

    def _check_queue_items(self, item):
        # if it's a directory
        # check if there is a mirror item exists in db
        # if yes, update status to syncd
        # else, create the mirror directory
        if item.is_dir():
            if not db.file_exists(item):
                log.trace("New directory:", item)
                if db.mirror_exists(item):
                    log.trace("Mirror directory exists in database. ", item)
                    log.trace("Sync OK:", item)
                else:
                    # directories need to be created first before their children
                    self._sync_queue.append( (Task.create, item) )
        else:
            # database contains all the syncd items
            # check if current file props matches with the saved props
            if db.file_exists(item):
                # get the file info as saved in database
                dbFile = db.get_file_as_db(item)

                # check if file props are still same
                if not item.same_file(dbFile):
                    log.say("File changed:", item)
                    # if already a mirror, sync them
                    if db.mirror_exists(item): 
                        mirror = db.get_mirror(item)
                        if not item.same_file(mirror):
                            log.say("Mirror changed:", item)
                            self._sync_queue.append( (Task.update, item) )
                    else:
                        log.trace("Downloading/Uploading mirror file", item)
                        self._sync_queue.append( (Task.load, item) )
                else:
                    # if no change at all or if a new file
                    # log.trace("No change found", item)
                    pass
            else:
                log.trace("New file:", item)
                if db.mirror_exists(item):
                    mirror = db.get_mirror(item)
                    if not item.same_file(mirror):
                        log.say("Mirror changed:", item)
                        self._sync_queue.append( (Task.update, item) )
                    else:
                        # log.trace("No change: ", item.path)
                        pass
                else:
                    log.say("Download/Upload:", item)
                    self._sync_queue.append( (Task.load, item) )

    def _execute(self):
        while self._sync_queue:
            task, item = self._sync_queue.pop(0)

            try:
                mirror = db.get_mirror(item)
            except ErrorParentNotFound:
                log.warn("No mirror parent directory exists in database. Might be an untracked item.", item)
                continue

            if task == Task.create:
                mirror.create_dir()
                db.add(item)
                db.add(mirror)

            elif task == Task.update:
                self._sync_files(item, mirror)

            elif task == Task.load:
                db.add(item)
                mirror = item.upload_or_download(mirror)
                db.add(mirror)

    def run(self):
        """ Process sync queue """
        log.say("Running SyncQ: ", len(self._check_queue), "items")

        while self._check_queue:
            self._check_queue_items(self._check_queue.pop(0))

        # if len(self._sync_queue):
        #     self.login()
        #     self._execute()

        log.say("Finish SyncQ")

    def _sync_files(self, item, mirror):
        """ Sync the item with it's mirror file. 
            Do extensive checking to modified time to determine sync direction.
            If modification detected in both local and remote, abort syncing. """
        log.trace("Syncing", item, " and ", mirror)

        iModified = item.modifiedTime()
        mModified = mirror.modifiedTime()

        lmodified = None 
        rmodified = None

        dbItem = db.get_file_as_db(item)
        dbMirr = db.get_file_as_db(mirror)

        if iModified > dbItem.modifiedTime():
            lmodified = True
        
        if rmodified > dbMirr.modifiedTime():
            rmodified = True

        if iModified > mModified:
            log.say("Uploading ", item.name, " ==> ", mirror.name)
            if lmodified:
                item.update(mirror)
            else:
                log.error("Could not detect previous local modification time. Aborting upload to avoid possible conflicts and data loss.")

        elif iModified < mModified:
            log.say("Downloading ", item.name, " <== ", mirror.name)
            if rmodified:
                mirror.update(item)
            else:
                log.error("Could not detect previous remote modification time. Aborting download to avoid possible conflicts and data loss.")
