import os
import sys
from pathlib import Path
import dateutil.parser

import pdb

from . import log, auth, utils, filesystem
from .remote_fs import GDriveFS
from .local_fs import LinuxFS

# Initialize

class PyGDCli:
    def __init__(self, settings_file = '.settings.json'):
        self.settings_file = settings_file
        self.settings = None
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.db = None
        self.objects = {}

        # local sync directory
        self.local_root = None

        # remote sync directory, NOT the root of Google Drive
        self.remote_root = None

    def read_settings(self):
        self.settings = utils.AttrDict()

        # settings file
        if os.path.isfile(self.settings_file):
            log.trace("Reading ", self.settings_file)
            self.settings.load_json(self.settings_file)
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
            self.settings.db_file = 'db.json'
            log.trace("Set database file: ", self.settings.db_file)

        # save the default settings
        self.settings.save(self.settings_file)

    def load_db(self):
        # read the database containing time, id, and mirror info
        if os.path.isfile(self.settings.db_file):
            self.db = utils.load_dict(self.settings.db_file)

            for key in self.db:
                if self.db[key]['modifiedTime']:
                    self.db[key]['modifiedTime'] = dateutil.parser.parse(self.db[key]['modifiedTime'])

                if self.db[key]['syncTime']:
                    self.db[key]['syncTime'] = dateutil.parser.parse(self.db[key]['syncTime'])
            log.say("Database loaded: ", self.settings.db_file)

        else:
            self.db = None
            log.warn("No previously saved database found: ", self.settings.db_file)

    def save_db(self):
        tree = {}
        if self.local_root:
            # local objects
            tree.update(self.local_root.tree())
        if self.remote_root:
            # remote objects
            tree.update(self.remote_root.tree())
        utils.save_dict(tree, self.settings.db_file)
        log.say("Saved database: ", self.settings.db_file)

    def setup_remote(self):
        """ Pre login items """
        if not self.settings:
            raise ValueError("Settings not loaded.")
        auth.set_scopes(self.scopes)

    def login(self):
        """ Get/update token, authenticate. """
        if not self.settings:
            raise ValueError("Settings not loaded.")
        auth.authenticate(self.settings.credentials_file, self.settings.token_pickle)

    def read_local_root(self):
        """ Get the latest local sync directory (root) files info. """

        self.local_root = LinuxFS(self.settings.local_root_path)
        self.local_root.list_dir(recursive=True)
        self.local_root.print_children()

    def read_remote_root(self):
        """ Get the latest remote sync directory (root) files info. """
        if not 'remote_root_id' in self.settings:
            log.say("Trying to resolve remote root path ", self.settings.remote_root_path)
            self.remote_root = GDriveFS.directory_from_path(self.settings.remote_root_path)
            if self.remote_root:
                self.settings.remote_root_id = self.remote_root.id
                self.settings.save(self.settings_file)
            else:
                log.critical("Can not determine remote path.")
                exit(1)
        else:
            self.remote_root = GDriveFS()
            # set the id of the remote sync directory and declare it a directory
            self.remote_root.set_id(self.settings.remote_root_id, True)

        # recursively query remote directory file list
        self.remote_root.list_dir(recursive=True)

        # print the root items only
        self.remote_root.print_children()

    def restore_mirrors(self, local_dir, remote_dir):
        """ Setup previously saved mirror links from database.
            @todo: rewrite this
        """
        local_dir.set_mirror(remote_dir)

        if self.db is None:
            return

        for local_child in local_dir.children:
            if local_child.mirror is None:
                if local_child.id in self.db:
                    mirror_id = self.db[local_child.id]['mirror']
                    for remote_child in remote_dir.children:
                        if mirror_id == remote_child.id:
                            local_child.set_mirror(remote_child)
                            log.trace('Set mirror: ', local_child.name, " <==> ", remote_child.name)

        for remote_child in remote_dir.children:
            if remote_child.mirror is None:
                if remote_child.id in self.db:
                    mirror_id = self.db[remote_child.id]['mirror']
                    for local_child in local_dir.children:
                        if mirror_id == local_child.id:
                            remote_child.set_mirror(local_child)
                            log.trace('Set mirror: ', remote_child.name, " <==> ", local_child.name)

    def setup_sync(self):
        """ Prepare and query both local and remote roots to get latest info. """
        self.load_db() 
        self.read_local_root()
        self.read_remote_root()
        self.restore_mirrors(self.local_root, self.remote_root)

    def sync_file(self, item):
        """ Sync the item with it's mirror file. 
            Do extensive checking to modified time to determine sync direction.
            If modification detected in both local and remote, abort syncing. """

        if isinstance(item, LinuxFS):
            localfile = item
            remotefile = item.mirror
        elif isinstance(item, GDriveFS):
            localfile = item.mirror
            remotefile = item
        else:
            raise TypeError("Sync object must be either LinuxFS or GDriveFS", item)

        if localfile is None or remotefile is None:
            raise ValueError("Sync item not valid", item)

        ltime = localfile.modifiedTime()
        rtime = remotefile.modifiedTime()

        local_db_modifiedTime = None
        if self.db and localfile.id in self.db:
            if 'modifiedTime' in self.db[localfile.id]:
                local_db_modifiedTime = self.db[localfile.id]['modifiedTime']

        local_db_syncTime = None
        if self.db and localfile.id in self.db:
            if 'syncTime' in self.db[localfile.id]:
                local_db_syncTime = self.db[localfile.id]['syncTime']

        remote_db_modifiedTime = None
        if self.db and remotefile.id in self.db:
            if 'modifiedTime' in self.db[remotefile.id]:
                remote_db_modifiedTime = self.db[remotefile.id]['modifiedTime']

        remote_db_syncTime = None
        if self.db and remotefile.id in self.db:
            if 'syncTime' in self.db[remotefile.id]:
                remote_db_syncTime = self.db[remotefile.id]['syncTime']

        lmodified = False
        rmodified = False

        if local_db_modifiedTime is None:
            log.warn("No time info about local file on database. Be careful with your files!", localfile)
        else:
            if local_db_syncTime is None:
                if ltime > local_db_modifiedTime:
                    log.say("Local file ", localfile.name, " has been modified.")
                    lmodified = True
                else:
                    log.error("DB time or local modification time invalid. Something is not quite right.", localfile)
            else:
                if ltime > local_db_syncTime:
                    log.say("Local file ", localfile.name, " has been modified.")
                    lmodified = True
                else:
                    log.error("DB time or local sync time invalid. Something is not quite right.", localfile)

        if remote_db_modifiedTime is None:
            log.warn("No time info about remote file on database. Be careful with your files!", remotefile)
        else:
            if remote_db_syncTime is None:
                if ltime > remote_db_modifiedTime:
                    log.say("remote file ", remotefile.name, " has been modified.")
                    rmodified = True
                else:
                    log.error("DB time or remote modification time invalid. Something is not quite right.", remotefile)
            else:
                if ltime > remote_db_syncTime:
                    log.say("remote file ", remotefile.name, " has been modified.")
                    rmodified = True
                else:
                    log.error("DB time or remote sync time invalid. Something is not quite right.", remotefile)

        if lmodified and rmodified:
            log.error("Both local and remote files have been modified. Can not decide sync direction.", localfile)
            #@todo: download remote and save as a copy, upload local and save as a copy
            return False

        if ltime > rtime:
            log.say("Uploading ", localfile.name, " ==> ", remotefile.name)
            if lmodified:
                localfile.gdrive_update(remotefile)
            else:
                log.error("Could not detect previous local modification time. Aborting upload to avoid possible conflicts and data loss.")

        elif ltime < rtime:
            log.say("Downloading ", localfile.name, " <== ", remotefile.name)
            if rmodified:
                remotefile.download_to_local(localfile)
            else:
                log.error("Could not detect previous remote modification time. Aborting download to avoid possible conflicts and data loss.")

        else:
            log.error("Can not determine the latest file, timestamp error", localfile, remotefile)


    def sync_roots(self):
        """ Check and run sync on both remote and local sync directories (roots). """

        if not self.local_root or not self.remote_root:
            raise RuntimeError("Roots not set.")

        if not self.sync_dir(self.remote_root):
            log.say("No change detected, files are in sync.")

    def sync_dir(self, directory_object, parent_object=None):
        """ Check and recursively run sync on a directory object. """

        if not isinstance(directory_object, filesystem.FileSystem):
            raise TypeError("Not a FileSystem object.", directory_object)

        if not directory_object.is_dir():
            raise ValueError("Can not sync a single file, need a directory.", directory_object)

        if directory_object.mirror is None:
            raise ValueError("No mirror set, sync will be one way only.", directory_object)

        change_detected = False

        if directory_object.is_local():
            if parent_object is None:
                parent_object = self.remote_root

            if self._upload_recursive(directory_object, parent_object):
                change_detected = True

            if self._download_recursive(directory_object.mirror, parent_object.mirror):
                change_detected = True

        else:
            if parent_object is None:
                parent_object = self.local_root

            log.trace("Recursively checking ", directory_object)
            # pdb.set_trace()                                                 # < ========================================= pdb
            if self._download_recursive(directory_object, parent_object):
                change_detected = True
            else:
                log.trace("No changes found for ", directory_object)

            log.trace("Recursively checking ", directory_object.mirror)
            if self._upload_recursive(directory_object.mirror, parent_object.mirror):
                change_detected = True
            else:
                log.trace("No changes found for ", directory_object.mirror)

        return change_detected


    def _find_mirror_in_parent(self, file, remote_parent):
        # this will fail if folder has multiple files with the 
        # same name
        for child in remote_parent.children:
            if file.name == child.name:
                return child
        return None

    def _download_recursive(self, remote_directory, local_mirror_parent):

        change_detected = False

        if not local_mirror_parent.exists:
            raise ValueError("Mirror parent does not exists.", local_mirror_parent)

        log.say("Checking remote directory for changes: ", remote_directory.name)

        if remote_directory.mirror is None:
            log.trace("Local mirror not set: ", remote_directory.name)
            # check the local file lists if same directory exists under mirror parent
            mirror = self._find_mirror_in_parent(remote_directory, local_mirror_parent)
            if mirror is None or not mirror.exists:
                # create it
                mirror = LinuxFS(os.path.join(local_mirror_parent.path, remote_directory.name))
                mirror.add_parent(local_mirror_parent.id)
                mirror.create_dir()

            remote_directory.set_mirror(mirror)
            log.trace("Set mirror ", mirror, " <==> ", remote_directory)
            change_detected = True
        else:
            log.trace("Mirror OK: ", remote_directory.name, " <==> ", remote_directory.mirror.path)

        for remote_child in remote_directory.children:
            if remote_child.is_dir():
                # recursively download child directory
                if self._download_recursive(remote_child, remote_directory.mirror):
                    change_detected = True
            else:
                sync = False
                download = False

                # no local mirror set, either a new remote file or new database
                if remote_child.mirror is None:
                    # check if file with the same name exists in the mirror directory
                    mirror = self._find_mirror_in_parent(remote_child, remote_directory.mirror)
                    if mirror is None or not mirror.exists:
                        download = True
                    else:
                        # it exists, check if contents are same
                        remote_child.set_mirror(mirror)
                        sync = True
                else:
                    # local mirror set, it must have been linked before
                    # if local file is not downloaded yet, do it
                    if not remote_child.mirror.exists:
                        download = True
                    else:
                        sync = True

                if download:
                    log.say("Downloading file ", remote_child)
                    change_detected = True
                    remote_child.download_to_parent(remote_directory.mirror)
                elif sync and not remote_child.same_file():
                    log.say("Not in sync: ", remote_child.name, remote_child.mirror.name)
                    change_detected = True
                    self.sync_file(remote_child)

        return change_detected


    def _upload_recursive(self, local_directory, remote_mirror_parent):

        change_detected = False

        if not remote_mirror_parent.exists:
            raise ValueError("Mirror parent does not exists.", remote_mirror_parent)

        log.say("Checking local directory for changes: ", local_directory.path)

        # check if remote mirror directory exists, or create it
        if local_directory.mirror is None:
            mirror = self._find_mirror_in_parent(local_directory, remote_mirror_parent)
            if mirror is None or not mirror.exists:
                mirror = GDriveFS()
                mirror.add_parent(remote_mirror_parent.id)
                mirror.create_dir()
            local_directory.set_mirror(mirror)
            change_detected = True

        for local_child in local_directory.children:
            if local_child.is_dir():
                # recursively upload child directory
                if self._upload_recursive(local_child, local_directory.mirror):
                    change_detected = True
            else:
                sync = False
                upload = False

                # no info recorded in db, either a new file or new database
                if local_child.mirror is None:
                    # check if file with the same name exists in the mirror directory
                    mirror = self._find_mirror_in_parent(local_child, local_directory.mirror)
                    if mirror is None or not mirror.exists:
                        upload = True
                    else:
                        # it exists, check if contents are same
                        local_child.set_mirror(mirror)
                        sync = True
                else:
                    # remote mirror set, it must have been linked before
                    # if remote file is not uploaded yet, do it
                    if not local_child.mirror.exists:
                        upload = True
                    else:
                        sync = True

                if upload:
                    log.say("Uploading file ", local_child)
                    change_detected = True
                    local_child.gdrive_upload(local_directory.mirror)
                elif sync and not local_child.same_file():
                    log.say("Not in sync: ", local_child.name, local_child.mirror.name)
                    change_detected = True
                    self.sync_file(local_child)

        return change_detected


def run():
    app = PyGDCli('settings.json')

    app.read_settings()
    app.setup_remote()
    app.login()

    app.setup_sync()
    app.sync_roots()

    app.save_db()

