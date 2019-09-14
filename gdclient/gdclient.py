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
        self.sync = sync.Sync(SCOPES, self.settings)

    def read_settings(self):
        self.settings = utils.AttrDict()

        # settings file
        if os.path.isfile(self.settings_file):
            log.trace("Reading ", self.settings_file)
            try:
                self.settings.load_json(self.settings_file)
            except:
                log.critical(
                    "Failed to read settings file. Please make sure the json format is valid.")
                raise
        else:
            log.say("Not found ", self.settings_file)

        os_home = str(Path.home())

        # save the default token file
        if not 'token_pickle' in self.settings:
            # self.settings.token_pickle = os.path.join(os_home, '.gdcli.token.pkl')
            self.settings.token_pickle = '.gdcli-token.pk'
            log.trace("Set token file: ", self.settings.token_pickle)

        if not 'credentials_file' in self.settings:
            cred_file = os.path.join(os.path.dirname(os.path.dirname(
                os.path.realpath(__file__))), "credentials.json")
            self.settings.credentials_file = cred_file
            log.trace("Set credentials file: ", self.settings.credentials_file)

        if not 'local_root_path' in self.settings:
            self.settings.local_root_path = os.getcwd()
            log.trace("Set local root: ", self.settings.local_root_path)

        if not 'remote_root_path' in self.settings:
            self.settings.remote_root_path = '/'
            log.trace("Set remote root: ", self.settings.remote_root_path)

        if not 'db_file' in self.settings:
            self.settings.db_file = '.gdcli-db.sqlite'
            log.trace("Set database file: ", self.settings.db_file)

        if not 'ignore_paths' in self.settings:
            self.settings.ignore_paths = [".gdcli*"]

        # save the default settings
        if not os.path.isfile(self.settings_file):
            self.settings.save(self.settings_file)
            log.say("Settings file created: ", self.settings_file)
            log.say("Please update the defaults and rerun.")
            sys.exit(0)

    def build_local_tree(self):
        """ Recursively build tree of local sync directory. """

        self.local_root = LinuxFS(self.settings.local_root_path, True)
        self.local_root.list_dir(recursive=True)
        # self.local_root.print_children()

    def build_remote_tree(self):
        """ Recursively build tree of remote sync directory. """

        if not 'remote_root_id' in self.settings:
            log.say("Resolving remote root path ",
                    self.settings.remote_root_path)
            self.remote_root = GDriveFS.remote_path_object(
                self.settings.remote_root_path)
            if self.remote_root:
                self.settings.remote_root_id = self.remote_root.id
                self.settings.save(self.settings_file)
            else:
                log.critical("Can not determine remote path.")
                exit(1)
        else:
            self.remote_root = GDriveFS()
            self.remote_root.set_path_id(
                self.settings.remote_root_path, self.settings.remote_root_id, True)

        # recursively query remote directory file list
        self.remote_root.list_dir(recursive=True)

        # print the root items only
        self.remote_root.print_children()

    def _add_sync_recursive(self, directory):
        """ Recursively go over directory contents and add
            to sync queue for processing. """

        count = 0
        if not isinstance(directory, filesystem.FileSystem):
            raise ErrorNotFileSystemObject(directory)

        if not directory.is_dir():
            raise NotADirectoryError(directory)

        log.progressdot("Scanning ", directory.path)

        if not db.file_exists(directory):
            log.trace("New directory:", directory)
            self.sync.add(directory)
            db.update_status(directory, db.Status.queued)
            count += 1

        # add children, recursively
        for child in directory.children:
            if child.is_dir():
                count += self._add_sync_recursive(child)
            else:
                if not db.file_exists(child):
                    log.trace("New file:", directory)
                    self.sync.add(child)
                    db.update_status(child, db.Status.queued)
                    count += 1

        return count

    def _add_sync_database(self):
        """ Load all local items from database and add to 
            sync queue if change detected. """

        log.say("Scanning local files for changes.")
        count = 0
        for item in db.get_all_local():
            dbFile = db.get_file_as_db(item)
            log.progressdot(dbFile.path)
            if item.exists:
                if not item.same_file(dbFile):
                    log.trace("Change found:", item)
                    self.sync.add(item)
                    count += 1
            else:
                item.trashed = True
                log.trace("File deleted:", item)
                self.sync.add(item)
                count += 1

        log.say("%d local file changes found." % count)

    def _add_sync_remote_changes(self):
        """ Fetch the remote changes and add to sync 
            queue for processing. """

        log.say("Querying remote changes with last change token: ",
                self.settings.get('lastChangeToken'))
        count = 0
        dG = GDChanges(self.settings.get('lastChangeToken'))
        for remote_change in dG.fetch():
            self.sync.add(remote_change)
            count += 1
        log.say("%d remote file changes found." % count)
        self.settings.lastChangeToken = dG.last_poll_token()

    def run(self, full_scan=False):
        if full_scan or db.is_empty():
            # Assuming nothing exists in the db
            # Populate it with local and remote items
            log.say("Running full recursive scan, this may take a while.")

            # recursively check the local files
            self.build_local_tree()
            self._add_sync_recursive(self.local_root)
            db.add(self.local_root)

            # Fetch remote items tree
            self.sync.login()
            self.build_remote_tree()
            self._add_sync_recursive(self.remote_root)
            db.add(self.remote_root)
        else:
            log.say("Checking for new files.")
            # recursively check the local files
            self.build_local_tree()
            n = self._add_sync_recursive(self.local_root)
            log.say(n, "new local files found.")

            # add database items to queue
            self._add_sync_database()

            # fetch remote changes and add to queue
            self.sync.login()
            self._add_sync_remote_changes()

        # start syncing
        self.sync.run()

        db.close()
        self.settings.save(self.settings_file)
        print()
