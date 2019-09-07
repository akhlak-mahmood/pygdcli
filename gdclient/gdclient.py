import os
import sys
from pathlib import Path 

from . import log
from . import utils
from . import sync
from . import filesystem
from . import database as db 

from .errors import *
from .local_fs import LinuxFS
from .remote_fs import GDriveFS, GDChanges

SCOPES = ["https://www.googleapis.com/auth/drive"]

log.set_max_level(log.DEBUG)

class PyGDClient:
    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.settings = None
        self.local_root = None 
        self.remote_root = None

        # read the settings file
        self.read_settings()

        # make sure settings are loaded
        if not self.settings:
            raise RuntimeError("Failed to detect settings.")

        # connect database, setup tables if needed
        db.connect(self.settings.db_file,
                    self.settings.remote_root_path,
                    self.settings.local_root_path)

        # connect remote server, login
        self.sync = sync.Sync(SCOPES,
                        self.settings.credentials_file,
                        self.settings.token_pickle)

    def read_settings(self):
        self.settings = utils.AttrDict()

        # settings file
        if os.path.isfile(self.settings_file):
            log.trace("Reading ", self.settings_file)
            try:
                self.settings.load_json(self.settings_file)
            except:
                log.critical("Failed to load settings file.")
                raise
        else:
            log.info("Not found ", self.settings_file)

        os_home = str(Path.home())

        # save the default token file
        if not 'token_pickle' in self.settings:
            # self.settings.token_pickle = os.path.join(os_home, '.gdcli.token.pkl')
            self.settings.token_pickle = 'token.pickle'
            log.trace("Set token file: ", self.settings.token_pickle)

        if not 'credentials_file' in self.settings:
            # we will move the default to os_home later
            # self.settings.credentials_file = os.path.join(os_home, '.gdcli.credentials.json')
            self.settings.credentials_file = 'credentials.json'
            log.trace("Set credentials file: ", self.settings.credentials_file)

        if not 'local_root_path' in self.settings:
            self.settings.local_root_path = os.getcwd()
            log.trace("Set local root: ", self.settings.local_root_path)

        if not 'remote_root_path' in self.settings:
            self.settings.remote_root_path = '/Photos'
            log.trace("Set remote root: ", self.settings.remote_root_path)

        if not 'db_file' in self.settings:
            self.settings.db_file = 'db.sqlite'
            log.trace("Set database file: ", self.settings.db_file)

        # save the default settings
        self.settings.save(self.settings_file)

    def build_local_tree(self):
        self.local_root = LinuxFS(self.settings.local_root_path, True)
        self.local_root.list_dir(recursive=True)
        # self.local_root.print_children()

    def build_remote_tree(self):
        if not 'remote_root_id' in self.settings:
            log.say("Resolving remote root path ", self.settings.remote_root_path)
            self.remote_root = GDriveFS.remote_path_object(self.settings.remote_root_path)
            if self.remote_root:
                self.settings.remote_root_id = self.remote_root.id
                self.settings.save(self.settings_file)
            else:
                log.critical("Can not determine remote path.")
                exit(1)
        else:
            self.remote_root = GDriveFS()
            self.remote_root.set_path_id(self.settings.remote_root_path, self.settings.remote_root_id, True)

        # recursively query remote directory file list
        self.remote_root.list_dir(recursive=True)

        # print the root items only
        self.remote_root.print_children()

    def _add_sync_recursive(self, directory):
        if not isinstance(directory, filesystem.FileSystem):
            raise ErrorNotFileSystemObject(directory)

        if not directory.is_dir():
            raise NotADirectoryError(directory)

        log.trace("Processing directory ", directory.path)

        self.sync.add(directory)
        db.update_status(directory, db.Status.queued)

        # add children, recursively
        for child in directory.children:
            if child.is_dir():
                self._add_sync_recursive(child)
            else:
                self.sync.add(child)
                db.update_status(child, db.Status.queued)

    def _add_sync_database(self):
        for fp in db.get_all_items():
            self.sync.add(fp)
        log.trace("Added database items to SyncQ")

    def _add_sync_remote_changes(self):
        log.trace("Added reported remote changes to SyncQ, not implemented")
        pass

    def run(self):

        if db.is_empty():
            # Assuming nothing exists in the db
            # Populate it with local and remote items
            log.say("Setting up database tree")

            # recursively check the local files
            self.build_local_tree()
            self._add_sync_recursive(self.local_root)

            self.sync.login()

            # Fetch remote items tree
            self.build_remote_tree()

            db.add(self.local_root)
            db.add(self.remote_root)

            # recursively add all remote files to queue
            self._add_sync_recursive(self.remote_root)
        else:
            log.say("Checking for changes.")
            # recursively check the local files
            self.build_local_tree()
            self._add_sync_recursive(self.local_root)

            # add database items to queue
            self._add_sync_database()

            # fetch remote changes and add to queue
            self._add_sync_remote_changes()

        # print(self.sync)

        # start syncing
        self.sync.run()

        print(self.sync)

        db.close()
        self.settings.save(self.settings_file)
