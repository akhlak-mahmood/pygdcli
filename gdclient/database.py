import datetime
from peewee import *

from . import log 
from . import filesystem

from .errors import *
from .local_fs import LinuxFS
from .remote_fs import GDriveFS

_db = SqliteDatabase(None)

class Status:
	queued	= 1
	synced	= 2
	deleted = 3

class FileType:
	LinuxFS = 'LinuxFS'
	DriveFS = 'DriveFS'

class BaseModel(Model):
	class Meta:
		database = _db

class File(BaseModel):
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

	# One of the types from Class Status
	# Update this field once it's set to queue and synced
	status 		= IntegerField(index=True)

	mimeType	= CharField(max_length=64)

	time_added	= DateTimeField(default=datetime.datetime.now)
	time_modified 	= DateTimeField(null=True)
	time_synced		= DateTimeField(null=True)

	# Applies to files only, not directories
	md5			= CharField(max_length=33, constraints=[Check('is_dir=0')], null=True)
	size		= IntegerField(constraints=[Check('is_dir=0')], null=True)


def connect(database_file):
	""" Initialize the database, connect, create tables if needed.
		Return the database object. """

	if _db.is_closed():
		_db.init(database_file)
		_db.connect()
		_db.create_tables([File])
		log.say("Database connect OK")


#@todo: rewrite these db functions for better performance

def _db_object_from_file(fileObj):
	if not isinstance(fileObj, filesystem.FileSystem):
		raise ErrorNotFileSystemObject(fileObj)

	if fileObj.path is None:
		raise ErrorPathResolve(fileObj)

	fp = File()

	if isinstance(fileObj, LinuxFS):
		fp.fstype = FileType.LinuxFS
	elif isinstance(fileObj, GDriveFS):
		fp.fstype = FileType.DriveFS

	fp.path 	= fileObj.path
	fp.is_dir	= fileObj.is_dir()

	return fp

def _file_object_from_db(dbObj):
	fp = None
	if dbObj.fstype == FileType.LinuxFS:
		fp = LinuxFS(dbObj.path)
		fp._is_dir = dbObj.is_dir
	elif dbObj.fstype == FileType.DriveFS:
		fp = GDriveFS()
		fp.set_path_id(dbObj.path, dbObj.id_str)

	return fp

def add(item):
	fp = _db_object_from_file(item)
	if fp.select().count() > 0:
		log.warn("Database add, already exists: ", fp.path)
		return

	fp.name 	= item.name
	fp.id_str 	= item.id
	fp.status 	= 0
	fp.mimeType = item.mimeType
	fp.time_modified = item.modifiedTime()
	fp.time_synced = None

	if item.is_file():
		fp.md5 = item.md5()
		fp.size = item.size()

	fp.save()
	log.trace("Database add OK: ", item)

def is_empty():
	return File.select().limit(1).count() == 0

def file_exists(item):
	fp = _db_object_from_file(item)
	return fp.select().count() > 0

def get_file_by_id(idn):
	dbObj = File.select().where(File.id_str == idn)
	return _file_object_from_db(dbObj[0])

def update_status(item, status):
	if not isinstance(status, Status):
		raise TypeError("Not a Status type object.", status)

	fp = _db_object_from_file(item)
	fp.status = status
	fp.save()

def close():
	global _db
	_db.commit()
	_db.close()
	log.trace("Database close OK")
