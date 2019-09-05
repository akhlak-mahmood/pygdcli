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


def add(item):
	if not isinstance(item, filesystem.FileSystem):
		raise ErrorNotFileSystemObject(item)

	if item.path is None:
		raise ErrorPathResolve(item)

	fp = File()
	fp.name 	= item.name

	if isinstance(item, LinuxFS):
		fp.fstype = FileType.LinuxFS
	elif isinstance(item, GDriveFS):
		fp.fstype = FileType.DriveFS

	fp.path 	= item.path
	fp.id_str 	= item.id
	fp.is_dir	= item.is_dir()
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

def path_exists():
	pass 

def get_path_by_id():
	pass

def update_status(item, status):
	pass

def save():
	global _db
	_db.commit()
	_db.close()
	log.trace("Database close OK")
