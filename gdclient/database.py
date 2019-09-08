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
	queued		= 1
	synced		= 2
	modified 	= 3

class FileType:
	LinuxFS = 'LinuxFS'
	DriveFS = 'DriveFS'

class BaseModel(Model):
	class Meta:
		database = _db

class Record(BaseModel):
	# Basename of the file
	name 		= CharField(max_length=256)

	# Filesystem type: LinuxFS or DriveFS
	fstype		= CharField(max_length=16)

	# We will match mirrors using paths
	path		= CharField(max_length=4096, index=True)

	# If filesystem has an id instead of path
	id_str		= CharField(max_length=512, index=True, null=True)

	# This should be set at the beginning
	is_dir		= BooleanField(default=False)

	deleted		= BooleanField(default=False)

	# One of the types from Class Status
	# Update this field once it's set to queue and synced
	status 		= IntegerField(index=True)

	mimeType	= CharField(max_length=64, null=True)

	time_added		= DateTimeField(default=datetime.utcnow)
	time_modified 	= DateTimeField(null=True)
	time_updated	= DateTimeField(null=True)

	# Applies to files only, not directories
	md5			= CharField(max_length=33, null=True)
	size		= IntegerField(null=True)


def connect(database_file, remote_root_path, local_root_path):
	""" Initialize the database, connect, create tables if needed.
		Return the database object. """
	global _remote_root, _local_root

	_remote_root	= remote_root_path
	_local_root		= local_root_path

	if _db.is_closed():
		_db.init(database_file)
		_db.connect()
		_db.create_tables([Record])
		log.say("Database connect OK:", database_file)


#@todo: rewrite these db functions for better performance
def _try_path_resolve(fileObj):
	name = fileObj.name 
	if isinstance(fileObj, GDriveFS):
		parentIds = fileObj.parentIds
	try:
		parent = get_file_by_id(parentIds[0])
		return os.path.join(parent.path, name)
	except:
		raise ErrorPathResolve(fileObj)

def _db_object_from_file(fileObj):
	if not isinstance(fileObj, filesystem.FileSystem):
		raise ErrorNotFileSystemObject(fileObj)

	if fileObj.path is None:
		fileObj.path = _try_path_resolve(fileObj)

	fp = Record()

	if isinstance(fileObj, LinuxFS):
		fp.fstype = FileType.LinuxFS
	elif isinstance(fileObj, GDriveFS):
		fp.fstype = FileType.DriveFS

	fp.path 	= fileObj.path
	fp.is_dir	= fileObj.is_dir()
	fp.name 	= fileObj.name
	fp.id_str 	= fileObj.id
	fp.status 	= 0
	fp.mimeType = fileObj.mimeType()
	fp.time_modified 	= fileObj.modifiedTime()
	fp.time_updated 	= None

	if fileObj.is_file():
		fp.md5 = fileObj.md5()
		fp.size = fileObj.size()

	fp.time_updated = datetime.utcnow()
	return fp

def _bare_file_object_from_db(dbObj):
	fp = None
	if dbObj.fstype == FileType.LinuxFS:
		fp = LinuxFS(dbObj.path, dbObj.is_dir)
	elif dbObj.fstype == FileType.DriveFS:
		fp = GDriveFS()
		fp.set_path_id(dbObj.path, dbObj.id_str, dbObj.is_dir)

	return fp

def _file_object_from_db(dbObj):
	dbRecord = _bare_file_object_from_db(dbObj)
	dbRecord.id = dbObj.id_str
	dbRecord.path = dbObj.path 
	dbRecord.name = dbObj.name
	dbRecord._md5 = dbObj.md5
	dbRecord._size = dbObj.size
	dbRecord._is_dir = dbObj.is_dir
	dbRecord.syncTime = dbObj.time_updated
	dbRecord._mimeType = dbObj.mimeType
	dbRecord._modifiedTime = dbObj.time_modified
	return dbRecord


def _get_rows(dbObj):
	return Record.select().where(
				(Record.path == dbObj.path) &
				(Record.is_dir == dbObj.is_dir) &
				(Record.fstype == dbObj.fstype) &
				(Record.deleted == False)
			)

def add(item):
	""" Add if not exists. """
	fp = _db_object_from_file(item)
	results = _get_rows(fp)
	if results.count() > 0:
		log.trace("Database add, already exists: ", fp.path)
		return False
	else:
		fp.save()
		log.trace("Database add OK: ", item)
		return True

def update(item):
	fstype = FileType.LinuxFS if isinstance(item, LinuxFS) else FileType.DriveFS
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
	fstype = FileType.LinuxFS if isinstance(item, LinuxFS) else FileType.DriveFS
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
	log.trace("Record set to deleted in database:", item)

def is_empty():
	return Record.select().limit(10).count() < 3

def file_exists(item):
	fstype = FileType.LinuxFS if isinstance(item, LinuxFS) else FileType.DriveFS
	results = Record.select().where(
		(Record.path == item.path) &
		(Record.is_dir == item.is_dir()) &
		(Record.fstype == fstype) &
		(Record.deleted == False)
	)
	return results.count() > 0

def get_file_as_db(item):
	""" Return a db object with info as saved in database. """
	dbObj = _db_object_from_file(item)
	results = _get_rows(dbObj)
	return _file_object_from_db(results[0]) if results.count() > 0 else None

def get_file_by_id(idn):
	dbObj = Record.select().where(Record.id_str == idn)
	return _file_object_from_db(dbObj[0]) if dbObj.count() > 0 else None

def get_row_by_id(idn):
	results = Record.select().where(Record.id_str == idn)
	return results[0] if results.count() > 0 else None

def get_all_items():
	results = Record.select().where(Record.deleted == False)
	return [_file_object_from_db(r) for r in results]

def get_all_local():
	results = Record.select().where(
		(Record.deleted == False) &
		(Record.fstype == FileType.LinuxFS)
	)
	return [LinuxFS(r.path, r.is_dir) for r in results]

def _db_mirror_from_file(item):
	item = _db_object_from_file(item)
	mirror = Record()

	# fix relative path
	if item.fstype == FileType.DriveFS:
		mirror.fstype = FileType.LinuxFS
		path = os.path.relpath(item.path, _remote_root)
		path = os.path.join(_local_root, path)
	else:
		mirror.fstype = FileType.DriveFS
		path = os.path.relpath(item.path, _local_root)
		path = os.path.join(_remote_root, path)

	mirror.path = os.path.normpath(path)

	mirror.is_dir = item.is_dir
	mirror.deleted = False
	return mirror

def calculate_mirror(item):
	try:
		mirror = _db_mirror_from_file(item)
		return _bare_file_object_from_db(mirror)
	except ErrorPathResolve:
		return None

def _find_db_object_parent_as_file(dbObj):
	if not isinstance(dbObj, Record):
		dbObj = _db_object_from_file(dbObj)

	results = Record.select().where(
		(Record.is_dir == True) &
		(Record.fstype == dbObj.fstype) &
		(Record.deleted == False) &
		(Record.path == os.path.dirname(dbObj.path))
	)
	if results.count() == 0:
		return None 
	else:
		return _bare_file_object_from_db(results[0])

def mirror_exists(item):
	""" If mirror item actually exists in database. """
	mirror = _db_mirror_from_file(item)
	results = _get_rows(mirror)
	return results.count() > 0

def get_mirror(item):
	""" Calculate mirror properties without checking if it
		exists. Only parent needs to exist. """
	mirror = _db_mirror_from_file(item)
	if mirror.fstype == FileType.DriveFS:
		parent = _find_db_object_parent_as_file(mirror)
		if parent is None:
			mirror = _bare_file_object_from_db(mirror)
			raise ErrorParentNotFound(item)
		mirror = _bare_file_object_from_db(mirror)
		mirror.add_parent_id(parent.id)
	else:
		mirror = _bare_file_object_from_db(mirror)

	return mirror

def update_status(item, status):
	fstype = FileType.LinuxFS if isinstance(item, LinuxFS) else FileType.DriveFS
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
