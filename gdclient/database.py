import os
from datetime import datetime
from peewee import *

from . import log
from . import filesystem

from .errors import *
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

_local_root = None
_remote_root = None
_db = SqliteDatabase(None)


class Status:
    queued = 1
    synced = 2
    modified = 3


class FileType:
    LinuxFS = 'LinuxFS'
    DriveFS = 'DriveFS'


class BaseModel(Model):
    class Meta:
        database = _db


class Record(BaseModel):
    # Basename of the file
    name = CharField(max_length=256)

    # Filesystem type: LinuxFS or DriveFS
    fstype = CharField(max_length=16)

    # We will match mirrors using paths
    path = CharField(max_length=4096, index=True)

    # If filesystem has an id instead of path
    id_str = CharField(max_length=512, index=True, null=True)

    # This should be set at the beginning
    is_dir = BooleanField(default=False)

    deleted = BooleanField(default=False)

    # One of the types from Class Status
    # Update this field once it's set to queue and synced
    status = IntegerField(index=True)

    mimeType = CharField(max_length=64, null=True)

    time_added = DateTimeField(default=datetime.utcnow)
    time_modified = DateTimeField(null=True)
    time_updated = DateTimeField(null=True)

    # Applies to files only, not directories
    md5 = CharField(max_length=33, null=True)
    size = IntegerField(null=True)


def connect(database_file, remote_root_path, local_root_path):
    """ Initialize the database, connect, create tables if needed.
            Return the database object. """
    global _remote_root, _local_root

    _remote_root = remote_root_path
    _local_root = local_root_path

    if _db.is_closed():
        _db.init(database_file)
        _db.connect()
        _db.create_tables([Record])
        log.say("Database connect OK:", database_file)

    return _db


def _record_object_from_file(fileObj):
    """ Given a FileSystem object, try to resolve it's
            path from parent IDs and parent record in database and
            return it as a Record object.
            Raises ErrorPathResolve """

    if not isinstance(fileObj, filesystem.FileSystem):
        raise ErrorNotFileSystemObject(fileObj)

    if fileObj.path is None and isinstance(fileObj, GDriveFS):
        parentIds = fileObj.parentIds
        try:
            parent = get_file_by_id(parentIds[0])
            fileObj.path = os.path.join(parent.path, fileObj.name)
        except:
            raise ErrorPathResolve(fileObj)

    dbRec = Record()

    if isinstance(fileObj, LinuxFS):
        dbRec.fstype = FileType.LinuxFS
    elif isinstance(fileObj, GDriveFS):
        dbRec.fstype = FileType.DriveFS

    dbRec.path = fileObj.path
    dbRec.is_dir = fileObj.is_dir()
    dbRec.name = fileObj.name
    dbRec.id_str = fileObj.id
    dbRec.status = 0
    dbRec.mimeType = fileObj.mimeType()
    dbRec.time_modified = fileObj.modifiedTime()
    dbRec.time_updated = None

    if fileObj.is_file():
        dbRec.md5 = fileObj.md5()
        dbRec.size = fileObj.size()

    dbRec.time_updated = datetime.utcnow()
    return dbRec


def _file_object_from_record(dbObj):
    """ Convert a database record into it's corresponding file object """

    if dbObj.fstype == FileType.LinuxFS:
        dbFile = LinuxFS(dbObj.path, dbObj.is_dir)
    elif dbObj.fstype == FileType.DriveFS:
        dbFile = GDriveFS()
        dbFile.set_path_id(dbObj.path, dbObj.id_str, dbObj.is_dir)

    dbFile.id = dbObj.id_str
    dbFile.path = dbObj.path
    dbFile.name = dbObj.name
    dbFile._md5 = dbObj.md5
    dbFile._size = dbObj.size
    dbFile._is_dir = dbObj.is_dir
    dbFile._syncTime = dbObj.time_updated
    dbFile._mimeType = dbObj.mimeType
    dbFile._modifiedTime = dbObj.time_modified
    return dbFile


def add(item):
    """ Add if not exists. """
    fstype = FileType.LinuxFS if isinstance(
        item, LinuxFS) else FileType.DriveFS
    results = Record.select().where(
        (Record.path == item.path) &
        (Record.is_dir == item.is_dir()) &
        (Record.fstype == fstype) &
        (Record.deleted == False)
    )
    if results.count() > 0:
        log.trace("Database add, already exists: ", item)
        return False
    else:
        fp = _record_object_from_file(item)
        fp.save()
        log.trace("Database add OK: ", item)
        return True


def update(item):
    """ Add or update a database record with the item's properties. """

    if not file_exists(item):
        add(item)

    fstype = FileType.LinuxFS if isinstance(
        item, LinuxFS) else FileType.DriveFS
    query = Record.update(
        name=item.name,
        id_str=item.id,
        md5=item.md5(),
        size=item.size(),
        mimeType=item.mimeType(),
        status=Status.synced,
        time_updated=datetime.utcnow(),
        time_modified=item.modifiedTime()
    ).where(
        (Record.path == item.path) &
        (Record.is_dir == item.is_dir()) &
        (Record.fstype == fstype) &
        (Record.deleted == False)
    )
    query.execute()
    log.trace("Record updated in database:", item)


def remove(item):
    """ Set deleted=True for an item in database """

    fstype = FileType.LinuxFS if isinstance(
        item, LinuxFS) else FileType.DriveFS
    query = Record.update(
        deleted=True,
        status=Status.synced,
        time_updated=datetime.utcnow(),
    ).where(
        (Record.path == item.path) &
        (Record.is_dir == item.is_dir()) &
        (Record.fstype == fstype) &
        (Record.deleted == False)
    )
    query.execute()
    log.trace("Database delete:", item)


def is_empty():
    """ Return true if database has less than 3 rows. """
    return Record.select().limit(10).count() < 3


def file_exists(item):
    fstype = FileType.LinuxFS if isinstance(
        item, LinuxFS) else FileType.DriveFS

    # convert to record object to resolve remote paths
    try:
        recItem = _record_object_from_file(item)
    except ErrorPathResolve:
        return False

    results = Record.select().where(
        (Record.path == recItem.path) &
        (Record.is_dir == recItem.is_dir) &
        (Record.fstype == fstype) &
        (Record.deleted == False)
    )
    return results.count() > 0


def resolve_path(item):
    """ Resolves the path of the file object from database.
        Raises ErrorPathResolve. """
    
    # convert to record object to resolve remote path
    recObj = _record_object_from_file(item)
    return _file_object_from_record(recObj)


def get_file_as_db(item):
    """ Return a file object with all the info as saved in database
            None if not found. """

    fstype = FileType.LinuxFS if isinstance(item, LinuxFS) else FileType.DriveFS
    results = Record.select().where(
                    (Record.path == item.path) &
                    (Record.is_dir == item.is_dir()) &
                    (Record.fstype == fstype) &
                    (Record.deleted == False)
            )

    if results.count() > 0:
        result = results[0]
        dbFile = filesystem.FileSystem()

        dbFile.id = result.id_str
        dbFile.path = result.path
        dbFile.name = result.name
        dbFile._md5 = result.md5
        dbFile._size = result.size
        dbFile._is_dir = result.is_dir
        dbFile._syncTime = result.time_updated
        dbFile._mimeType = result.mimeType
        dbFile._modifiedTime = result.time_modified
    else:
        return None

    # set GDrive type object's parent IDs
    if result.fstype == FileType.DriveFS and not dbFile.parentIds:
        parent_path = os.path.dirname(dbFile.path)
        results = Record.select().where(
                    (Record.path == parent_path) &
                    (Record.is_dir == True) &
                    (Record.fstype == FileType.DriveFS) &
                    (Record.deleted == False)
                )
        if results.count() > 0:
            dbFile.parentIds = [p.id_str for p in results]
    return dbFile


def get_file_by_id(idn):
    dbObj = Record.select().where(Record.id_str == idn)
    return _file_object_from_record(dbObj[0]) if dbObj.count() > 0 else None


def get_record_by_id(idn):
    results = Record.select().where(Record.id_str == idn)
    return results[0] if results.count() > 0 else None


def get_all_local():
    results = Record.select().where(
        (Record.deleted == False) &
        (Record.fstype == FileType.LinuxFS)
    )
    return [LinuxFS(r.path, r.is_dir) for r in results]


def calculate_mirror(item):
    """ Calculate an item's mirror path based on it's 
            parent id or path.
            Raises ErrorPathResolve on failure. """

    # try to resolve the item's path first
    itemRec = _record_object_from_file(item)
    mirror = Record()
    # fix relative path from sync root
    if itemRec.fstype == FileType.DriveFS:
        path = os.path.relpath(itemRec.path, _remote_root)
        path = os.path.join(_local_root, path)
        path = os.path.normpath(path)
        mirror = LinuxFS(path, itemRec.is_dir)
    else:
        mirror = GDriveFS()
        path = os.path.relpath(itemRec.path, _local_root)
        path = os.path.join(_remote_root, path)
        path = os.path.normpath(path)
        mirror.set_path_id(path, None, itemRec.is_dir)

    return mirror


def get_mirror(item):
    """ Return the mirror file object with parentIds """

    mirror = calculate_mirror(item)
    if isinstance(mirror, GDriveFS) and not mirror.parentIds:
        parent_path = os.path.dirname(mirror.path)
        results = Record.select().where(
            (Record.path == parent_path) &
            (Record.is_dir == True) &
            (Record.fstype == FileType.DriveFS) &
            (Record.deleted == False)
        )
        mirror.parentIds = [p.id_str for p in results]
    return mirror


def mirror_exists(item):
    """ If mirror item actually exists in database. """
    try:
        mirror = calculate_mirror(item)
    except ErrorPathResolve:
        return False
    return file_exists(mirror)


def update_status(item, status):
    fstype = FileType.LinuxFS if isinstance(
        item, LinuxFS) else FileType.DriveFS
    query = Record.update(
        status=status,
        time_updated=datetime.utcnow()
    ).where(
        (Record.path == item.path) &
        (Record.is_dir == item.is_dir()) &
        (Record.fstype == fstype) &
        (Record.deleted == False)
    )
    query.execute()


def close():
    global _db
    _db.commit()
    _db.close()
    log.say("Database close OK")
