import datetime
from peewee import *

from . import log 

_db = None

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
	name 		= CharField(maxlength=256)

	# Filesystem type: LinuxFS or DriveFS
	fstype		= CharField(maxlength=16)

	# We will match mirrors using paths
	path		= CharField(maxlength=4096, index=True)

	# If filesystem has an id instead of path
	id_str		= CharField(maxlength=512, index=True)

	# This should be set at the beginning
	is_dir		= BooleanField(default=False)

	# One of the types from Class Status
	# Update this field once it's set to queue and synced
	status 		= IntegerField(index=True)

	mimeType	= CharField(maxlength=64)

	time_added	= DateTimeField(default=datetime.datetime.now)
	time_modified 	= DateTimeField()
	time_synced		= DateTimeField()

	# Applies to files only, not directories
	md5			= CharField(maxlength=33, constraints=[Check('is_dir=0')])
	size		= IntegerField(constraints=[Check('is_dir=0')])


def connect(database_file):
	""" Initialize the database, connect, create tables if needed.
		Return the database object. """

	global _db

	if _db is None:
		_db = SqliteDatabase(database_file)
		_db.connect()
		_db.create_tables([File])
		log.say("Database connect OK")

	return _db


def add():
	pass 

def path_exists():
	pass 

def get_path_by_id():
	pass

def update_status(status):
	pass

def save():
	global _db
	_db.commit()
	_db.close()
	log.trace("Database close OK")
