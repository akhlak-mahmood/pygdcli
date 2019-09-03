import os
import io
import shutil
import dateutil.parser
from datetime import datetime

from googleapiclient.http import MediaIoBaseDownload

from . import log, auth, local_fs
from .filesystem import *

class GDriveFS(FileSystem):
    """ Google files/dirs handler class. """

    def __init__(self, gdFileObject=None):
        """ Initialize an empty class or with a response 
            object from GDrive api. """

        super().__init__()

        self.exists = False
        self._modifiedTime = None
        self._md5 = None

        if gdFileObject:
            # if a response object, parse basic properties
            self.gdFileObject = gdFileObject
            self._parse_object()

    def is_local(self):
        return False

    def modifiedTime(self):
        if self.exists and self.is_file():
            # parse the RFC 3339 time as python datetime with utc timezone
            return dateutil.parser.parse(self._modifiedTime)
        return None

    def md5(self):
        if self.is_dir():
            return None
        return self._md5

    def set_object(self, gdFileObject):
        """ If the file/dir was initialized as an empty object,
            set it's properties using a GDrive api response. """
        self.gdFileObject = gdFileObject
        self._parse_object()

    def set_root(self):
        """ Declare this as the root of the GDrive. """
        self.id = 'root'
        self.exists = True
        self._is_dir = True
        self.mimeType = MimeTypes.gdrive_directory

    def set_id(self, x, is_a_directory):
        """ If the file/dir was initialized as an empty object,
            set it's GDrive id. """
        self.id = x
        self.exists = True
        self._is_dir = is_a_directory

    def _parse_object(self):
        """ parse the common properties from the api response json. """
        if self.gdFileObject:
            # if has a valid id, it exists
            self.id = self._get_object_attr('id')
            self.name = self._get_object_attr('name')
            self._size = int(self._get_object_attr('size'))
            self._modifiedTime = self._get_object_attr('modifiedTime')
            self._md5 = self._get_object_attr('md5Checksum')
            self.exists = True

            self.mimeType = self._get_object_attr('mimeType')

            # it is necessary to set _is_dir property
            if self.mimeType == MimeTypes.gdrive_directory:
                self._is_dir = True
            else:
                self._is_dir = False

        else:
            self.exists = False
            raise ValueError("Can not parse gdFileObject, not set")

    def _get_object_attr(self, key):
        """ Helper function the iterate response dictionary. """
        if key in self.gdFileObject:
            return self.gdFileObject.get(key)
        else:
            return None


    def list_dir(self, nextPageToken=None):
        """ Populate the self.children items by sending an api request to GDrive. """
        if not self.id:
            raise RuntimeError("ID not set", self)

        if not self.is_dir():
            raise RuntimeError("Can not list, object is a file", self)

        if not self.exists:
            raise RuntimeError("Remote directory not exists", self)

        log.trace("Listing directory: ", self)

        if nextPageToken:
            log.trace("Fetching next page")
            results = auth.service.files().list(
                q="'%s' in parents and trashed = false" %self.id,
                fields=LSFIELDS,
                pageToken=nextPageToken,
                pageSize=50).execute()
        else:
            results = auth.service.files().list(
                q="'%s' in parents and trashed = false" %self.id,
                fields=LSFIELDS,
                pageSize=50).execute()

        if 'nextPageToken' in results:
            log.warn("List trancated, pagination needed, not implemented.")


        if not 'files' in results:
            log.error("No files item returned")
            raise RuntimeError(results)

        self.children = []
        for child in results['files']:
            childObj = GDriveFS(child)
            # explicitely set parent, since it can not be
            # determined from the path
            childObj.add_parent(self.id)
            self.children.append(childObj)

        log.say("List directory OK")

    def download_to_local(self, local_file):
        """ Download current remote file to a local file object and 
            set each other as mirrors. """

        if not isinstance(local_file, local_fs.LinuxFS):
            raise TypeError("Downloadable file not a local_fs.LinuxFS object")

        if local_file.is_dir() or self.is_dir():
            raise NotImplementedError("Can not download directory")

        if local_file.exists:
            # if the target local file already exist, make a backup of it
            # incase the download fails
            log.warn("Backing up local file")
            os.rename(local_file.path, local_file.path + '.bak')

        # download bytes to memory, may fail in case of huge files
        fh = self.download_to_memory()

        log.trace("Writing file ", local_file.path)

        # write memory byte to disk
        fh.seek(0)

        with open(local_file.path, 'wb') as f:
            shutil.copyfileobj(fh, f, length=WRITE_CHUNK_SIZE)

        local_file.exists = True
        self.set_mirror(local_file)

        # record sync time
        self.syncTime = datetime.now()
        local_file.syncTime = self.syncTime

        log.say("Save OK ", local_file.path)

        try:
            # remove the backup
            os.remove(local_file.path + ".bak")
        except:
            pass


    def download_to_memory(self):
        """ Download the file contents as bytes into memory. 
            This may fail if file size is larger than available memory.
            Returns a byteIO object, which works like a file stream.
        """

        if not self.id:
            raise ValueError("ID not defined to download", self)

        if self.is_dir():
            raise ValueError("Can not download directory to memory", self)

        else:
            log.say("Downloading: ", self.name, "ID: ", self.id)
            request = auth.service.files().get_media(fileId=self.id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()
                log.say("Downloaded %d%%." % int(status.progress() * 100))

            return fh


    def download_to_parent(self, parent_object):
        """ Download current remote file to a specified local directory. """

        if not isinstance(parent_object, local_fs.LinuxFS):
            raise TypeError("Parent object has to be a local_fs.LinuxFS object", parent_object)

        if not self.id:
            raise ValueError("id not set to download", self)

        if not self.name:
            raise ValueError("name not set to create local file", self)

        if not parent_object.is_dir():
            raise ValueError("parent object must be a directory", parent_object)

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
            raise TypeError("Parent not a GDriveFS object")

        parent.list_dir()

        for child in parent.children:
            if child.name == dir_name:
                return child

        return None

    @staticmethod
    def directory_from_path(gdrive_path):
        """ Given a GDrive path, file the remote object. 
            This is necessary to get the remote sync directory id. """

        paths = gdrive_path.split("/")

        # init empty remote object
        parent = GDriveFS()
        
        # path must start like 'root/path/to/dir' or '/path/to/dir'
        if paths[0] != 'root' and not gdrive_path.startswith("/"):
            raise ValueError("Invalid gdrive_path")
        else:
            # declare parent as root
            parent.set_root()

        if gdrive_path == "/" or gdrive_path == "root":
            return parent
        
        for dir_name in paths[1:]:
            directory = GDriveFS._get_child_dir(parent, dir_name)

            if directory is None:
                # path doesn't exist in remote
                #@todo: create it?
                log.warn("Path not found: ", gdrive_path)
                return None

            if directory.is_file():
                log.warn("Specified path is a file, taking parent directory as the path ", gdrive_path)
                break

            log.trace("Resolved path: ", parent, dir_name)
            parent = directory

        return parent

