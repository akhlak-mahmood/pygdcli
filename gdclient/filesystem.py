import json

UPLOAD_CHUNK_SIZE = 1024*1024
WRITE_CHUNK_SIZE = 131072

FIELDS = "id,size,name,mimeType,modifiedTime,parents,md5Checksum"
LSFIELDS = "nextPageToken, files(%s)" %FIELDS

class MimeTypes:
    linux_directory = 'inode/directory'
    gdrive_directory = 'application/vnd.google-apps.folder'


class FileSystem:
    def __init__(self):
        self.name = None
        self.path = None
        self.id = None
        self.parents = None
        self.children = []
        self.mirror = None
        self.mimeType = None
        self.exists = None
        self._is_dir = None
        self._size = None
        self.syncTime = None

    def is_dir(self):
        if self._is_dir is None:
            raise ValueError("Object type information not set. ", str(self))
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

    def mimeType(self):
        return self.mimeType

    def add_parent(self, parent_id):
        if self.parents is None:
            self.parents = []

        if isinstance(parent_id, FileSystem):
            raise TypeError("parent must be an id/path")

        self.parents.append(parent_id)

    def set_mirror(self, FS_object):
        if not isinstance(FS_object, FileSystem):
            raise TypeError("Must be a FileSystem type object")
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

        # items to save in json database
        items[self.id] = {
            "type":         self.__class__.__name__,
            "directory":    self.is_dir(),
            "name":         self.name,              
            "mimeType":     self.mimeType,          
            "parents":      self.parents,           
            "mirror":       mirror,                 
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
        items = self.__repr__()

        if self.is_dir():
            for child in self.children:
                items.update(child.tree()) 

        return items

    def same_file(self):
        if self.is_dir():
            raise ValueError("Can not compare directory")

        if not self.mirror:
            raise ValueError("No mirror item set to compare")

        if not isinstance(self.mirror, FileSystem):
            raise TypeError("Mirror is not an object")

        size = self.size()
        if not size:
            raise RuntimeError("Failed to determine size")

        if size != self.mirror.size():
            return False

        md5 = self.md5()
        if not md5:
            raise RuntimeError("Failed to determine md5")

        if md5 != self.mirror.md5():
            return False

        return True
