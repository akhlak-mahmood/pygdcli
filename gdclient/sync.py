import os

from . import log 
from . import auth
from . import database as db 

from .errors import *
from .filesystem import FileSystem
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

class Task:
    nochange    = 0
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
        """ Add an item to sync queue for checking """
        if not isinstance(item, FileSystem):
            raise ErrorNotFileSystemObject(item)

        # if type and path not in queue
        if not any(x for x in self._check_queue if all([x.path == item.path, x.__class__ == item.__class__])):
            self._check_queue.append(item)

    def get_Qmirror(self, item):
        """ Return and remove the mirror item from the queue if exists. """
        try:
            mirror = db.calculate_mirror(item)
        except ErrorPathResolve:
            return None
        qmirrors = [x for x in self._check_queue if all([x.path == mirror.path, x.__class__ == mirror.__class__])]
        Qmirror = qmirrors[0] if len(qmirrors) else None
        try:
            # remove mirror from queue to avoid double handling
            self._check_queue.remove(Qmirror)
        except:
            # "easier to ask for forgiveness than permission"
            pass

        return Qmirror

    def _check_queue_items(self, item):
        """ Check an item for update, creation etc and set to
            corresponding task queue. """
        if db.file_exists(item):
            # change, no change, delete
            dbFile = db.get_file_as_db(item)
            if not item.same_file(dbFile):
                # change or delete
                Qmirror = self.get_Qmirror(item)
                if Qmirror:
                    # change in both local and remote
                    if item.same_file(Qmirror):
                        # same in both local and remote
                        # no further processing needed
                        self._sync_queue.append((Task.nochange, item, Qmirror))
                    else:
                        # different changes in local and mirror
                        if item.is_file():
                            self._sync_queue.append((Task.conflict, item, Qmirror))
                        else:
                            self._sync_queue.append((Task.nochange, item, Qmirror))
                else:
                    # delete in either local or remote
                    if item.trashed:
                        self._sync_queue.append((Task.delete, item, None))
                    else:
                        # change
                        self._sync_queue.append((Task.update, item, None))
        else:
            # new file, new setup
            Qmirror = self.get_Qmirror(item)
            if Qmirror:
                # item both in local and remote
                if item.same_file(Qmirror):
                    # same in both local and remote
                    # no further processing needed
                    self._sync_queue.append((Task.nochange, item, Qmirror))
                else:
                    # different version
                    if item.is_file():
                        self._sync_queue.append((Task.conflict, item, Qmirror))
                    else:
                        self._sync_queue.append((Task.nochange, item, Qmirror))
            else:
                # new file or directory
                if item.is_file():
                    self._sync_queue.append((Task.load, item, None))
                else:
                    self._sync_queue.append((Task.create, item, None))

    def _execute(self):
        """ Run the set task for the queue items. """
        while self._sync_queue:
            task, item, Qmirror = self._sync_queue.pop(0)

            try:
                mirror = db.get_mirror(item)
            except ErrorPathResolve:
                log.warn("Failed to find path:", item)
                # ignore
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

            elif task == Task.delete:
                db.remove(item)
                if db.mirror_exists(item):
                    mirror.remove()
                    db.remove(mirror)

            elif task == Task.conflict:
                self.resolve_conflict(item, Qmirror)
                # db.add(item)
                # db.add(Qmirror)
            else:
                # no change
                db.add(item)
                db.add(Qmirror)


    def run(self):
        """ Process sync queue """
        log.say("Running SyncQ: ", len(self._check_queue), "items")

        while self._check_queue:
            self._check_queue_items(self._check_queue.pop(0))

        if len(self._sync_queue):
            print(self)
            input("Press Enter to execute changes: ")
            self.login()
            self._execute()

        log.say("Finish SyncQ")

    def _sync_files(self, item, mirror):
        """ Sync the item with it's mirror file. 
            Do extensive checking to modified time to determine sync direction.
            If modification detected in both local and remote, abort syncing. """
        log.trace("Syncing:", item, " ==> ", mirror)

        dbItem = db.get_file_as_db(item)

        # current file modification time is later than
        # the one saved in database
        if item.modifiedTime() > dbItem.modifiedTime():
            mirror = item.update(mirror)
            db.update(item)
            db.update(mirror)

    def resolve_conflict(self, item, mirror):
        log.warn("Conflict between", item, "and", mirror)
        print("1. Keep", item)
        print("2. Keep", mirror)
        print("Anything else: skip")

        try:
            i = int(input("Please choose: "))
        except:
            i = None

        if i == 1:
            log.trace("Syncing:", item, " ==> ", mirror)
            mirror = item.update(mirror)
            db.update(item)
            db.update(mirror)
        elif i == 2:
            log.trace("Syncing:", mirror, " ==> ", item)
            item = mirror.update(item)
            db.update(mirror)
            db.update(item)
