import json

UPLOAD_CHUNK_SIZE = 1024*1024
WRITE_CHUNK_SIZE = 131072

FIELDS = "id,size,name,mimeType,modifiedTime,parents,md5Checksum"
LSFIELDS = "nextPageToken, files(%s)" %FIELDS
CHFIELDS = "nextPageToken,newStartPageToken,changes/file(%s)" %FIELDS

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
        self.mirror = None
        self.mimeType = None
        self.exists = None
        self._is_dir = None
        self._size = None
        self.syncTime = None

    def is_dir(self):
        if self._is_dir is None:
            # self._is_dir must be set for each item explicitely
            raise ValueError("Object type information (file or directory) not set. ", str(self))
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

    def modifiedTime(self):
        raise NotImplementedError()

    def md5(self):
        raise NotImplementedError()

    def set_mirror(self, FS_object):
        """ Attach another file object as a mirror so we can sync them easily. """
        if not isinstance(FS_object, FileSystem):
            raise TypeError("Must be a FileSystem type object to set mirror.")

        if self.is_dir() != FS_object.is_dir():
            raise TypeError("Can not set mirror between directory and file.", self, FS_object)

        self.mirror = FS_object
        FS_object.mirror = self

    def __repr__(self):
        items = {}
        mirror = self.mirror.id if self.mirror else None

        modifiedTime = None
        if self.modifiedTime():
            modifiedTime = self.modifiedTime().strftime("%Y-%m-%d %H:%M:%S.%f+00:00 (UTC)")

        syncTime = None
        if self.syncTime:
            syncTime = self.syncTime.strftime("%Y-%m-%d %H:%M:%S.%f+00:00 (UTC)")

        # items to save in json database or on print(self)
        items[self.id] = {
            "type":         self.__class__.__name__,
            "directory":    self.is_dir(),
            "name":         self.name,              
            "mimeType":     self.mimeType,          
            "size":         self.size(),            
            "modifiedTime": modifiedTime,           
            "syncTime":     syncTime,              
            "md5":          self.md5()
        }

        return items

    def __str__(self):
        return self.__repr__().__str__()


    def print_children(self):
        print("No.  DIR \t NAME \t\t md5 \t modifiedTime")
        print("-----------------------------------------------------------------")
        for i, child in enumerate(self.children):
            modifiedTime = None
            if child.modifiedTime():
                modifiedTime = child.modifiedTime().strftime("%Y-%m-%d %H:%M:%S.%f+00:00 (UTC)")
            print("%d   %s \t %s \t\t %s \t %s" %(i+1, child.is_dir(), child.name, child.md5(), modifiedTime))


    def tree(self):
        """ Returns a dictionary containing all the basic properties of a
            file, and recursively if it's a directory. Can be used to save
            and load later. """
        items = self.__repr__()

        if self.is_dir():
            for child in self.children:
                items.update(child.tree()) 

        return items

    def same_file(self):
        """ Compare a file with it's mirror file. """

        if self.is_dir():
            raise ValueError("Can not compare directory")

        if not self.mirror:
            raise ValueError("No mirror item set to compare")

        if not isinstance(self.mirror, FileSystem):
            raise TypeError("Mirror is not an object")

        size = self.size()
        if not size:
            raise RuntimeError("Failed to determine size")

        # If size is not same, they can't be the same
        if size != self.mirror.size():
            return False

        # Finally check md5 hash of the file contents
        md5 = self.md5()
        if not md5:
            raise RuntimeError("Failed to determine md5")

        if md5 != self.mirror.md5():
            return False

        #@todo: add byte by byte comparison option if md5 not available

        return True
