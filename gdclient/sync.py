import os

from . import log 
from . import auth
from . import database as db 

from .errors import *
from .filesystem import FileSystem
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

class Task:
    create      = 1
    load        = 2
    update      = 3
    delete      = 4
    conflict    = 5

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
        if not any(x for x, y in self._check_queue if all([x.path == item.path, x.__class__ == item.__class__])):
            self._check_queue.append(item)

    def get_Qmirror(self, item):
        if isinstance(item, LinuxFS):
            mirrors = [x for x in self._check_queue if all([x.path == item.path, x.__class__ == GDriveFS])]
        elif isinstance(item, GDriveFS):
            mirrors = [x for x in self._check_queue if all([x.path == item.path, x.__class__ == LinuxFS])]

        mirror = mirrors[0] if len(mirrors) else None
        try:
            # remove mirror from queue to avoid double handling
            self._check_queue.remove(mirror)
        except:
            # "easier to ask for forgiveness than permission"
            pass

        return mirror

    def _check_queue_items(self, item):
        if db.file_exists(item):
            # change, no change, delete
            dbFile = db.get_file_as_db(item)
            if not item.same_file(dbFile):
                # change or delete
                Qmirror = self.get_Qmirror(item)
                if Qmirror:
                    # change in both local and remote
                    if item.same_file(Qmirror):
                        # same change!!
                        db.update(item)
                        db.update(Qmirror)
                    else:
                        # different changes in local and mirror
                        self.resolve_conflict(item, Qmirror)
                else:
                    # delete in either local or remote
                    if item.trashed:
                        db.remove(item)
                        if db.mirror_exists(item):
                            mirror = db.get_mirror()
                            mirror.remove()
                            db.remove(mirror)
                    else:
                        # change
                        mirror = db.get_mirror(item)
                        self._sync_files(item, mirror)
        else:
            # new file, new setup
            Qmirror = self.get_Qmirror(item)
            if Qmirror:
                # item both in local and remote
                if item.same_file(Qmirror):
                    # same in both local and remote
                    db.add(item)
                    db.add(Qmirror)
                else:
                    # different version
                    self.resolve_conflict(item, Qmirror)
                    db.add(item)
                    db.add(Qmirror)
            else:
                # new file
                mirror = db.get_mirror(item)
                item.upload_or_download(mirror)
                db.add(item)
                db.add(mirror)

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

    def resolve_conflict(self, item, mirror):
        log.warn("Conflict between", item, "and", mirror, "NOT IMPLEMENTED")
        return
