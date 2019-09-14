import json
import dateutil

UPLOAD_CHUNK_SIZE = 1024*1024
WRITE_CHUNK_SIZE = 131072

FIELDS = "id,size,name,mimeType,modifiedTime,parents,md5Checksum,trashed"
LSFIELDS = "nextPageToken, files(%s)" % FIELDS
CHFIELDS = "nextPageToken,newStartPageToken,changes/file(%s)" % FIELDS


class MimeTypes:
    linux_directory = 'inode/directory'
    gdrive_directory = 'application/vnd.google-apps.folder'


class FileSystem:
    """ The base file system class to keep track of the common
        properties of individual file items. """

    def __init__(self):
        self.name = None
        self.path = None
        self.id = None
        self.children = []
        self.parentIds = None
        self.exists = None
        self._is_dir = None
        self._size = None
        self._syncTime = None
        self._md5 = None
        self._mimeType = None
        self._modifiedTime = None
        self.trashed = False

    def is_dir(self):
        if self._is_dir is None:
            # self._is_dir must be set for each item explicitely
            raise ValueError(
                "Object type information (file or directory) not set.")
        return self._is_dir

    def is_file(self):
        if self.is_dir() is None:
            return None
        else:
            return not self.is_dir()

    def is_local(self):
        raise NotImplementedError()

    def is_remote(self):
        if self.is_local() is None:
            return None
        else:
            return not self.is_local()

    def list_dir(self):
        raise NotImplementedError()

    def size(self):
        return self._size

    def mimeType(self):
        return self._mimeType

    def modifiedTime(self):
        if self._modifiedTime and type(self._modifiedTime) == str:
            return dateutil.parser.parse(self._modifiedTime)
        return self._modifiedTime

    def syncTime(self):
        if self._syncTime and type(self._syncTime) == str:
            return dateutil.parser.parse(self._syncTime)
        return self._syncTime

    def md5(self):
        return self._md5

    def __repr__(self):
        text = [
            self.__class__.__name__,
            "D" if self.is_dir() else "F",
            # str(self.name),
            # str(self.md5()),
            str(self.path)
        ]
        return "::".join(text)

    def __str__(self):
        return self.__repr__()

    def print_children(self):
        print("No.  DIR \t NAME \t\t md5 \t modifiedTime")
        print("-----------------------------------------------------------------")
        for i, child in enumerate(self.children):
            modifiedTime = None
            if child.modifiedTime():
                modifiedTime = child.modifiedTime().strftime("%Y-%m-%d %H:%M:%S.%f+00:00 (UTC)")
            print("%d   %s \t %s \t\t %s \t %s" %
                  (i+1, child.is_dir(), child.name, child.md5(), modifiedTime))

    def same_file(self, mirror):
        """ Compare a file with it's mirror file. """

        if self.trashed != mirror.trashed:
            return False

        if self.is_dir():
            return self.path == mirror.path

        if not isinstance(mirror, FileSystem):
            raise TypeError("Mirror is not a FileSystem object", mirror)

        # If size is not same, they can't be the same
        if self.size() != mirror.size():
            return False

        if self.md5() != mirror.md5():
            return False

        # @todo: add byte by byte comparison option if md5 not available

        return True

    def upload_or_download(self, mirror):
        raise NotImplementedError()

    def update(self, mirror):
        raise NotImplementedError()

    def remove(self):
        raise NotImplementedError()
