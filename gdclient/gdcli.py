import os
import sys
from pathlib import Path
import dateutil.parser

from . import log, auth, utils
from .remote_fs import GDriveFS
from .local_fs import LinuxFS

# Initialize

class PyGDCli:
    def __init__(self, settings_file = '.settings.json'):
        self.settings_file = settings_file
        self.settings = None
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.db = None

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

        # save the default token file
        if not 'token_pickle' in self.settings:
            os_home = str(Path.home())
            # self.settings.token_pickle = os.path.join(os_home, '.gdcli.token.pkl')
            self.settings.token_pickle = os.path.join(os.getcwd(), 'token.pickle')
            log.trace("Set token file: ", self.settings.token_pickle)

        if not 'credentials_file' in self.settings:
            # we will move the default to os_home later
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

    def save_db(self):
        tree = {}
        if self.local_root:
            # local objects
            tree.update(self.local_root.tree())
        if self.remote_root:
            # remote objects
            tree.update(self.remote_root.tree())
        utils.save_dict(tree, self.settings.db_file)

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
        self.local_root.list_dir()
        self.local_root.print_children()

    def read_remote_root(self):
        """ Get the latest remote sync directory (root) files info. """
        if not 'remote_root_id' in self.settings:
            self.remote_root = GDriveFS.directory_from_path(self.settings.remote_root_path)
            if self.remote_root:
                self.settings.remote_root_id = self.remote_root.id
                self.settings.save(self.settings_file)
            else:
                log.critical("Can not determine remote path.")
                exit(1)
        else:
            self.remote_root = GDriveFS()
            self.remote_root.set_id(self.settings.remote_root_id, True)

        self.remote_root.list_dir()
        self.remote_root.print_children()

    def restore_mirrors(self, local_dir, remote_dir):
        """ Setup previously saved mirror links from database. """
        local_dir.set_mirror(remote_dir)
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

    def sync(self, item):
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
        if localfile.id in self.db:
            if 'modifiedTime' in self.db[localfile.id]:
                local_db_modifiedTime = self.db[localfile.id]['modifiedTime']

        local_db_syncTime = None
        if localfile.id in self.db:
            if 'syncTime' in self.db[localfile.id]:
                local_db_syncTime = self.db[localfile.id]['syncTime']

        remote_db_modifiedTime = None
        if remotefile.id in self.db:
            if 'modifiedTime' in self.db[remotefile.id]:
                remote_db_modifiedTime = self.db[remotefile.id]['modifiedTime']

        remote_db_syncTime = None
        if remotefile.id in self.db:
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


    def sync_root(self):
        """ Check and run sync on both remote and local sync directories (roots). """

        if not self.local_root or not self.remote_root:
            raise RuntimeError("Root not set")

        change_detected = False

        #@todo: iterate over local files and upload them

        # iterate over remote files
        for child in self.remote_root.children:
            # no local mirror set, must be a new remote file
            if child.mirror is None:
                change_detected = True
                child.download_to_parent(self.local_root)

            else:
                # local mirror set, it must have been linked before
                # if local file is not downloaded yet, do it
                if not child.mirror.exists:
                    change_detected = True
                    child.download_to_parent(self.local_root)
                else:
                    # local file exists, check if they are same
                    if not child.same_file():
                        change_detected = True
                        log.say("Not in sync: ", child.name, child.mirror.name)
                        # sync child with it's mirror
                        self.sync(child)

        if not change_detected:
            log.say("No change detected, files are in sync.")


def run():
    app = PyGDCli('settings.json')

    app.read_settings()
    app.setup_remote()
    app.login()

    app.setup_sync()
    app.sync_root()

    app.save_db()

