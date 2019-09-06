import os
import io
import hashlib
import mimetypes
from datetime import datetime
import pytz

from googleapiclient.http import MediaFileUpload

from . import log, auth, remote_fs
from .filesystem import *
from .errors import *

class LinuxFS(FileSystem):
    """ A linux specific file handler.
        Can upload files to Google Drive. """

    def __init__(self, path, is_dir=None):
        super().__init__()

        # use relative path from current working directory
        # so the sync folder can be moved around
        self.path = os.path.relpath(path)

        # for local fs, path is id
        self.id = self.path

        # We can create instance even if it doesn't exist yet
        self.exists = os.path.exists(self.path)
        self.name = os.path.basename(self.path)

        if self.exists:
            # this will set _is_dir
            self.guess_mimeType()

        # explicitly set is_dir if specified
        if is_dir is not None:
            self._is_dir = is_dir


    def is_local(self):
        return True

    def size(self):
        if not self.exists:
            return None
        if self.is_dir():
            return None

        return os.path.getsize(self.path)

    def create_dir(self):
        # declare this as a directory
        self._is_dir = True

        if self.exists:
            log.warn("Directory already exists: ", self)
            return
        else:
            os.makedirs(self.path)
            self.exists = True
            log.say("Created local directory: ", self.path)

    def md5(self):
        """ Calculate md5 by chunk, this should be okay with large files. """
        if self.is_dir() or not self.exists:
            return None

        md5 = hashlib.md5()
        with open(self.path, 'rb') as f:
            for chunk in iter(lambda: f.read(128 * md5.block_size), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def modifiedTime(self):
        if not self.exists:
            return None

        # get OS modified time
        t = os.path.getmtime(self.path)

        # convert unix epoch time string to datetime
        dt = datetime.utcfromtimestamp(int(t))

        # set utc timezone
        return pytz.UTC.localize(dt)

    def guess_mimeType(self):
        """ Naive way to guess the mimetype, fails always other
            than for some very common file types."""

        if not self.exists:
            raise ErrorPathNotExists(self)

        if os.path.isdir(self.path):
            self._is_dir = True
            self._mimeType = MimeTypes.linux_directory
        else:
            self._is_dir = False
            mmtype = None
            mmtype, encoding = mimetypes.guess_type(self.path)
            # if not mmtype:
            #     log.trace("Failed mimetype detect: ", self.path)
            self._mimeType = mmtype

    def list_dir(self, recursive=False):
        """ Populate self.children list by reading current directory items. """
        if not self.exists:
            raise ErrorPathNotExists(self)

        if self.is_file():
            raise NotADirectoryError(self)

        self.children = []
        for file in os.listdir(self.path):
            full_path = os.path.join(self.path, file)
            child = LinuxFS(full_path)
            self.children.append(child)

            # recursively read child directories
            if recursive and child.is_dir():
                child.list_dir(recursive=recursive)

    def gdrive_upload(self, parentIds):
        """ Upload a new file to G Drive. """

        if not self.exists:
            ErrorPathNotExists(self)

        if not self.is_file():
            raise IsADirectoryError(self)

        payload = {
            'name': self.name,
            'parents': parentIds
        }

        if not self._mimeType:
            self.guess_mimeType()

        media = MediaFileUpload(self.path, 
                mimetype = self._mimeType,
                chunksize = UPLOAD_CHUNK_SIZE,
                resumable = True
            )

        file = auth.service.files().create(
                body = payload,
                media_body = media,
                fields = FIELDS         # fields that will be returned in response json
            )

        response = None

        while response is None:
            status, response = file.next_chunk()
            if status:
                log.say("Uploaded %d%%" %int(status.progress() * 100))

        if file:
            # record sync time
            self.syncTime = datetime.now()
            log.say("Upload successful: ", self.path)
            return response
        else:
            log.error("Upload failed: ", response)
            return None

    def gdrive_update(self, remote_file):
        """ Update an existing G Drive file with a local file.
            @todo: update only bytes that changed.
            """

        if not self.exists:
            ErrorPathNotExists(self)

        if not isinstance(remote_file, remote_fs.GDriveFS):
            raise ErrorNotDriveFSObject(self)

        if not self.is_file():
            raise IsADirectoryError(self)

        payload = {
            'title': self.name,
        }

        media = MediaFileUpload(
                self.path,
                chunksize = UPLOAD_CHUNK_SIZE,
                resumable = True
            )

        file = auth.service.files().update(
                fileId = remote_file.id,
                body = payload,
                media_body = media,
                fields = FIELDS         # fields that will be returned in response json
            )

        response = None

        while response is None:
            status, response = file.next_chunk()
            if status:
                log.say("Uploaded %d%%" %int(status.progress() * 100))

        if file:
            # update the remote file properties with the response json
            remote_file.set_object(response)

            # set remote file as mirror of current file
            self.set_mirror(remote_file)

            # record sync time
            self.syncTime = datetime.now()
            remote_file.syncTime = self.syncTime

            log.say("Update successful: ", self.path)
            return True
        else:
            log.error("Update failed: ", response)
            return False


    def upload_or_download(self, mirror):
        if not isinstance(mirror, remote_fs.GDriveFS):
            raise ErrorNotDriveFSObject(mirror)

        response = self.gdrive_upload(mirror.parentIds)

        # path should be already set, so parent path is None
        mirror.set_object(response, None)

        return mirror
