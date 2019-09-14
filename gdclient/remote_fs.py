import os
import io
import shutil
import dateutil.parser
from datetime import datetime

from googleapiclient.http import MediaIoBaseDownload

from . import log, auth, local_fs
from .filesystem import *
from .errors import *


class GDriveFS(FileSystem):
    """ Google files/dirs handler class. """

    def __init__(self, gdFileObject=None, parent_path=None):
        """ Initialize an empty class or with a response 
            object from GDrive api. """

        super().__init__()

        self.exists = False
        self._modifiedTime = None
        self._md5 = None
        self.parentIds = None
        self.is_google_doc = None

        if gdFileObject:
            if parent_path is None:
                raise ErrorPathResolve("Parent path must be specified.", self)
            # if a response object, parse basic properties
            self.gdFileObject = gdFileObject
            self._parse_object(parent_path)

    def is_local(self):
        return False

    def create_dir(self):
        # 1. set_name() with parent path and dir name
        # 2. set_parent_ids()

        # declare this as a directory
        self._is_dir = True

        if self.exists:
            log.warn("Remote directory already exists: ", self)
            return True

        if self.name is None:
            raise ValueError("Name not set, can not create.", self)

        if self.path is None:
            raise ErrorPathResolve(self)

        if not self.parentIds or len(self.parentIds) == 0:
            raise ValueError(
                "Parent IDs not set, can not create directory.", self)

        # create directory file on gDrive
        body = {
            'name': self.name,
            'mimeType': MimeTypes.gdrive_directory,
            'parents': self.parentIds
        }

        response = auth.service.files().create(
            body=body,
            fields=FIELDS         # fields that will be returned in response json
        ).execute()

        if response:
            self.set_object(response, os.path.dirname(self.path)), None
            self.exists = True
            log.say("Created remote directory: ", self.path)
        else:
            raise RuntimeError("Failed to create remote directory.", response)

    def set_object(self, gdFileObject, parent_path):
        """ If the file/dir was initialized as an empty object,
            set it's properties using a GDrive api response. """
        self.gdFileObject = gdFileObject
        self._parse_object(parent_path)

    def set_name(self, parent_path, name, is_a_directory):
        """ If the file/dir was initialized as an empty object,
            set it's name and path. """
        self.name = name
        self._is_dir = is_a_directory
        self.path = os.path.join(parent_path, name)

    def set_path_id(self, path, idn, is_a_directory):
        """ If the file/dir was initialized as an empty object,
            set it's path and id number. """
        self.path = path

        # idn can be none when it's a dummy object
        if idn:
            self.id = idn
            self.exists = True          # file exists if it has an ID
        self._is_dir = is_a_directory
        self._mimeType = MimeTypes.gdrive_directory
        self.name = os.path.basename(self.path)

    def _parse_object(self, parent_path):
        """ parse the common properties from the api response json. """

        # if has a valid id, it exists
        self.id = self.gdFileObject.get('id')
        if self.id is None:
            raise ErrorParseResponseObject(self, self.gdFileObject)

        self.exists = True

        # we will resolve the path using name
        self.name = self.gdFileObject.get('name')
        if self.name is None:
            raise ErrorParseResponseObject(self, self.gdFileObject)

        # resolve remote path
        # if path is already set, ignore
        if self.path is None:
            if parent_path:
                self.path = os.path.join(parent_path, self.name)

        self._mimeType = self.gdFileObject.get('mimeType')
        self._modifiedTime = self.gdFileObject.get('modifiedTime')

        # store parents to upload later
        if self.gdFileObject.get('parents'):
            for p_id in self.gdFileObject.get('parents'):
                self.add_parent_id(p_id)

        # set _is_dir properly
        if self._mimeType == MimeTypes.gdrive_directory:
            self._is_dir = True
        else:
            self._is_dir = False

        self.trashed = self.gdFileObject.get('trashed', False)

        if self.is_file():
            try:
                self._size = int(self.gdFileObject.get('size'))
                self._md5 = self.gdFileObject.get('md5Checksum')
                self.is_google_doc = False
            except:
                # ignore, these files might be google docs
                # @todo: process google docs
                self.is_google_doc = True

    def add_parent_id(self, parent_id):
        """ A file/dir can have more than one parent directory. """
        if self.parentIds is None:
            self.parentIds = []

        self.parentIds.append(parent_id)

    def declare_gdrive_root(self):
        self.exists = True
        self.path = "/"
        self._is_dir = True
        self.name = "My Drive"
        self.id = 'root'

    def list_dir(self, nextPageToken=None, recursive=False):
        """ Populate the self.children items by sending an api request to GDrive. """
        if not self.id:
            raise RuntimeError("ID not set, can not list directory.", self)

        if not self.is_dir():
            raise NotADirectoryError("Can not list, object is a file.", self)

        if not self.exists:
            raise ErrorPathNotExists(
                "Remote directory does not exist, can not list.", self)

        if self.path is None:
            raise ErrorPathResolve(
                "Path not set, can not initialize children.", self)

        if nextPageToken:
            log.trace("List directory fetching next page: ", self.path)
            results = auth.service.files().list(
                q="'%s' in parents and trashed = false" % self.id,
                fields=LSFIELDS,
                pageToken=nextPageToken,
                pageSize=50).execute()
        else:
            log.trace("Listing directory: ", self.path)
            results = auth.service.files().list(
                q="'%s' in parents and trashed = false" % self.id,
                fields=LSFIELDS,
                pageSize=50).execute()

        # if it's not the first page of list dir,
        # append to children list, otherwise clear it
        if nextPageToken is None:
            self.children = []

        if results.get('files') is None:
            log.error("No files item returned, something is wrong.")
            raise RuntimeError(results)

        for child in results.get('files'):
            childObj = GDriveFS(child, self.path)
            self.children.append(childObj)

            # recursively read child directories
            if recursive and childObj.is_dir():
                childObj.list_dir(recursive=recursive)

        log.say("List directory OK: ", self.path)

        if 'nextPageToken' in results:
            self.list_dir(results.get('nextPageToken'), recursive)

    def download_to_local(self, local_file):
        """ Download current remote file to a local file object and 
            set each other as mirrors. """

        if not isinstance(local_file, local_fs.LinuxFS):
            raise ErrorNotLinuxFSObject(local_file)

        if local_file.is_dir() or self.is_dir():
            raise IsADirectoryError("Can not download directory")

        try:
            # download bytes to memory, may fail in case of huge files
            fh = self.download_to_memory()

            log.trace("Writing file ", local_file.path)

            # write memory byte to disk
            fh.seek(0)

            with open(local_file.path, 'wb') as f:
                shutil.copyfileobj(fh, f, length=WRITE_CHUNK_SIZE)

            local_file.exists = True
            log.say("Save OK ", local_file.path)
        except Exception as ex:
            log.error("Failed to download:", self.path)
            print(ex)
            return False

        # record sync time
        self._syncTime = datetime.utcnow()
        local_file._syncTime = self._syncTime

        return True

    def download_to_memory(self):
        """ Download the file contents as bytes into memory. 
            This may fail if file size is larger than available memory.
            Returns a byteIO object, which works like a file stream.
        """

        if not self.id:
            raise ValueError("ID not defined to download", self)

        if self.is_dir():
            raise IsADirectoryError(
                "Can not download directory to memory", self)

        else:
            log.say("Downloading: ", self.name, "ID: ", self.id)
            request = auth.service.files().get_media(fileId=self.id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            log.say("Downloading file:", self.name, "please wait ...")
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                log.progress("Downloaded %d%%." % int(status.progress() * 100))

            return fh

    def download_to_parent(self, parent_object):
        """ Download current remote file to a specified local directory. """

        if not isinstance(parent_object, local_fs.LinuxFS):
            raise ErrorNotLinuxFSObject(
                "Parent object has to be a local_fs.LinuxFS object", parent_object)

        if not self.id:
            raise ErrorIDNotSet(self)

        if not self.name:
            raise ErrorNameNotSet("name not set to create local file", self)

        if not parent_object.is_dir():
            raise NotADirectoryError(
                "parent object must be a directory.", parent_object)

        # find target local file path
        parent_dir = parent_object.path
        local_path = os.path.join(parent_dir, self.name)

        # create a new local file object
        local_file = local_fs.LinuxFS(local_path)

        # setting _is_dir is important
        local_file._is_dir = False

        self.download_to_local(local_file)

    @staticmethod
    def _get_child_dir(parent, dir_name):
        """ Helper function to determine if a remote file exists
            in a GDrive directory. """
        if not isinstance(parent, GDriveFS):
            raise ErrorNotDriveFSObject(parent)

        parent.list_dir()

        for child in parent.children:
            if child.name == dir_name:
                return child

        return None

    @staticmethod
    def remote_path_object(gdrive_path):
        """ Given a GDrive path, find the remote object. 
            This is necessary to get the remote sync directory id. """

        paths = gdrive_path.strip().split("/")

        # init empty remote object
        parent = GDriveFS()

        # path must start like 'root/path/to/dir' or '/path/to/dir'
        if paths[0] != 'root' and not gdrive_path.startswith("/"):
            raise ValueError("Invalid gdrive_path, must start with / or root/")
        else:
            parent.declare_gdrive_root()

        if gdrive_path == "/" or gdrive_path == "root":
            return parent

        for dir_name in paths[1:]:
            directory = GDriveFS._get_child_dir(parent, dir_name)

            if directory is None:
                # path doesn't exist in remote
                log.warn("Remote path does not exist: ", gdrive_path)
                return None

            parent = directory
            if directory.is_file():
                log.trace("Specified path is a file: ", gdrive_path)
                break

        log.say("Resolved path OK: ", parent.path)
        return parent

    def upload_or_download(self, mirror):
        self.download_to_local(mirror)
        return mirror

    def update(self, mirror):
        self.download_to_local(mirror)
        return mirror

    def remove(self):
        if not self.id:
            raise ErrorIDNotSet("Can not remove.")

        log.trace("Removing", self)
        try:
            # trash/delete is recursive
            # @todo: if directory, recursively remove children from DB as well
            updated_file = auth.service.files().update(fileId=self.id,
                                                       body={'trashed': True},
                                                       fields=FIELDS
                                                       ).execute()
        except Exception as ex:
            log.error(ex)
        else:
            self.set_object(updated_file, None)
            log.say("Trash OK:", self)


class GDChanges:
    def __init__(self, last_poll_token=None):
        self._changed_items = []
        if last_poll_token:
            self.startPageToken = last_poll_token
        else:
            log.trace("Getting changes startPageToken")
            response = auth.service.changes().getStartPageToken().execute()
            self.startPageToken = response.get('startPageToken')
            log.trace("Changes startPageToken OK")

    def _retrieve_changes(self):
        page_token = self.startPageToken

        while page_token is not None:
            response = auth.service.changes().list(
                pageToken=page_token,
                spaces='drive',
                fields=CHFIELDS
            ).execute()
            for change in response.get('changes'):
                item = GDriveFS()

                # setting parent as None, which needs to be resolved
                item.set_object(change.get('file'), None)

                self._changed_items.append(item)

            if 'newStartPageToken' in response:
                # Last page, save this token for the next polling interval
                self.startPageToken = response.get('newStartPageToken')

            page_token = response.get('nextPageToken')

    def fetch(self):
        self._changed_items = []
        self._retrieve_changes()
        return self._changed_items

    def last_poll_token(self):
        return self.startPageToken
