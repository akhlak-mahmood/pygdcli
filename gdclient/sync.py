import os
import fnmatch

from . import log
from . import auth
from . import database as db

from .errors import *
from .filesystem import FileSystem
from .local_fs import LinuxFS
from .remote_fs import GDriveFS


class Task:
    nochange = 0
    create = 1
    load = 2
    update = 3
    delete = 4
    conflict = 5


class Sync:
    def __init__(self, scopes, settings):
        self.scopes = scopes
        self.settings = settings
        self._login = False
        self._check_queue = []
        self._sync_queue = []

        self.setup_auth()

    def setup_auth(self):
        auth.set_scopes(self.scopes)

    def login(self):
        if not self._login:
            log.trace("Logging in to remote server.")
            auth.authenticate(self.settings.credentials_file, self.settings.token_pickle)
            self._login = True
            log.say("Authetication OK")
        else:
            log.trace("Already logged in to remote.")

    def __repr__(self):
        return "SyncQ items: \n" + "\n".join([str(i) for i in self._sync_queue])

    def add(self, item):
        """ Add an item to sync queue for checking """

        # if type and id not in queue, id is set to path for local files
        if not any(x for x in self._check_queue if all([x.id == item.id, x.__class__ == item.__class__])):
            try:
                item = db.resolve_path(item)
            except:
                # if path not resolved, file not within our directory, ignore
                log.trace("Failed to resolve path from DB: ", item)
            else:
                for ignore in self.settings.ignore_paths:
                    if fnmatch.fnmatch(item.name, ignore) or fnmatch.fnmatch(item.path, ignore):
                        log.say("Ignore: ", item)
                    else:
                        self._check_queue.append(item)
        else:
            log.trace("Already in queue:", item)

    def get_Qmirror(self, item):
        """ Return and remove the mirror item from the queue if exists. """
        try:
            mirror = db.calculate_mirror(item)
        except ErrorPathResolve:
            return None
        qmirrors = [x for x in self._check_queue if all(
            [x.path == mirror.path, x.__class__ == mirror.__class__])]
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
            log.trace("DB record found:", dbFile)

            if not item.same_file(dbFile):
                log.trace("Not same as DB:", item)
                # change or delete
                Qmirror = self.get_Qmirror(item)
                if Qmirror:
                    # change in both local and remote
                    if item.same_file(Qmirror):
                        log.trace("Local and remote changes same:", item)
                        # same in both local and remote
                        # no further processing needed
                        self._sync_queue.append((Task.nochange, item, Qmirror))
                    else:
                        # different changes in local and mirror
                        if item.is_file():
                            self._sync_queue.append(
                                (Task.conflict, item, Qmirror))
                        else:
                            self._sync_queue.append(
                                (Task.nochange, item, Qmirror))
                else:
                    # delete in either local or remote
                    if item.trashed:
                        self._sync_queue.append((Task.delete, item, None))
                        log.trace("Queued for deletion", item)
                    else:
                        # change
                        self._sync_queue.append((Task.update, item, None))
                        log.trace("Queued for sync", item)
            else:
                log.trace("File signature same as database:", item)
        else:
            log.trace("Not in DB:", item)
            # new file, new setup
            Qmirror = self.get_Qmirror(item)
            if Qmirror:
                # item both in local and remote
                if item.same_file(Qmirror):
                    # same in both local and remote
                    # no further processing needed
                    log.trace("Local and remote changes same:", item)
                    self._sync_queue.append((Task.nochange, item, Qmirror))
                else:
                    # different version
                    if item.is_file():
                        self._sync_queue.append((Task.conflict, item, Qmirror))
                    else:
                        self._sync_queue.append((Task.nochange, item, Qmirror))
            else:
                if not item.trashed:
                    # new file or directory
                    if item.is_file():
                        self._sync_queue.append((Task.load, item, None))
                        log.trace("Queued for download/upload", item)
                    else:
                        self._sync_queue.append((Task.create, item, None))
                        log.trace("Queued for creation", item)

    def _execute(self):
        """ Run the set task for the queue items. """
        while self._sync_queue:
            task, item, Qmirror = self._sync_queue.pop(0)

            log.trace("Processing", task, item)

            if task == Task.create:
                try:
                    mirror = db.calculate_mirror(item)
                    mirror.create_dir()
                    db.add(item)
                    db.add(mirror)
                except Exception as ex:
                    log.warn(type(ex).__name__)
                    log.warn("Task.create failed:", ex)

            elif task == Task.update:
                try:
                    # mirror must exists in db for updating
                    mirror = db.get_mirror(item)
                    self._sync_files(item, mirror)
                except Exception as ex:
                    log.warn(type(ex).__name__)
                    log.warn("Task.update failed:", ex)

            elif task == Task.load:
                # mirror existence in database is optional
                try:
                    mirror = db.calculate_mirror(item)
                    db.add(item)
                    mirror = item.upload_or_download(mirror)
                    db.add(mirror)
                except Exception as ex:
                    log.warn(type(ex).__name__)
                    log.warn("Task.load failed:", ex)

            elif task == Task.delete:
                try:
                    db.remove(item)
                    if db.mirror_exists(item):
                        mirror = db.get_mirror(item)
                        mirror.remove()
                        db.remove(mirror)
                except Exception as ex:
                    log.warn(type(ex).__name__)
                    log.warn("Task.delete failed:", ex)

            elif task == Task.conflict:
                try:
                    self.resolve_conflict(item, Qmirror)
                except Exception as ex:
                    log.warn(type(ex).__name__)
                    log.warn("Task.conflict failed:", ex)
            else:
                # no change
                db.update(item)
                db.update(Qmirror)

    def run(self):
        """ Process sync queue """
        log.say("Checking SyncQ: ", len(self._check_queue), "items")

        while self._check_queue:
            self._check_queue_items(self._check_queue.pop(0))

        log.say("SyncQ check complete.")

        if len(self._sync_queue):
            print(self)
            input("Press Enter to execute changes: ")
            self.login()
            self._execute()
        else:
            log.say("All files in sync, no action needed.")

        log.say("Finished Sync.")

    def _sync_files(self, item, mirror):
        """ Sync the item with it's mirror file. """
        log.trace("Syncing:", item, " ==> ", mirror)

        # syncing means file must exist in DB
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
            i = int(input("Please enter your choice: "))
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
