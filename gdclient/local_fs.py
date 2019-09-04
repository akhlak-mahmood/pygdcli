import os
import io
import hashlib
import mimetypes
from datetime import datetime
import pytz

from googleapiclient.http import MediaFileUpload

from . import log, auth, remote_fs
from .filesystem import *

class LinuxFS(FileSystem):
    """ A linux specific file handler.
        Can upload files to Google Drive. """

    def __init__(self, path):
        super().__init__()
        self.path = os.path.relpath(path)

        # for local fs, path is id
        self.id = self.path

        self.exists = os.path.exists(self.path)
        self.name = os.path.basename(self.path)
        self.add_parent(os.path.dirname(self.path))

        if self.exists:
            # this will also set _is_dir, otherwise algorithm will fail
            self.guess_mimeType()

    def is_local(self):
        return True

    def size(self):
        if self.exists and self.is_file():
            return os.path.getsize(self.path)

    def create_dir(self):
        # declare this as a directory
        self._is_dir = True

        if self.exists:
            log.warn("Directory already exists: ", self)
            return
        else:
            os.mkdir(self.path)
            self.exists = True
            log.say("Created local directory: ", self.path)

    def md5(self):
        """ Calculate md5 by chunk, should be okay with large files. """
        if self.is_dir():
            return None

        md5 = hashlib.md5()
        with open(self.path, 'rb') as f:
            for chunk in iter(lambda: f.read(128 * md5.block_size), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def modifiedTime(self):
        if self.exists:
            # get OS modified time
            t = os.path.getmtime(self.path)

            # convert unix epoch time string to datetime
            dt = datetime.utcfromtimestamp(int(t))

            # set utc timezone
            return pytz.UTC.localize(dt)
        else:
            return None

    def guess_mimeType(self):
        """ Naive way to guess the mimetype, fails always other
            than for some very common file types."""

        if not self.exists:
            raise RuntimeError("Not found ", self.path)
        if os.path.isdir(self.path):
            self._is_dir = True
            self.mimeType = MimeTypes.linux_directory
        else:
            self._is_dir = False
            mmtype = None
            mmtype, encoding = mimetypes.guess_type(self.path)
            # if not mmtype:
            #     log.trace("Failed mimetype detect: ", self.path)
            self.mimeType = mmtype

    def list_dir(self, recursive=False):
        """ Populate self.children list by reading current directory items. """
        if self.exists and self.is_dir():
            self.children = []
            for file in os.listdir(self.path):
                full_path = os.path.join(self.path, file)
                child = LinuxFS(full_path)
                self.children.append(child)

                # recursively read child directories
                if recursive and child.is_dir():
                    child.list_dir(recursive=recursive)
        else:
            log.warn("List directory failed: ", self.path)

    def gdrive_upload(self, remote_directory):
        """ Upload a new file to G Drive. """

        if not self.exists:
            raise RuntimeError("Upload failed, not found.", self.path)

        if not isinstance(remote_directory, remote_fs.GDriveFS):
            raise TypeError("Target parent directory must be a remote_fs.GDriveFS type.")

        if self.is_file():
            remote_file = remote_fs.GDriveFS()
            remote_file.add_parent(remote_directory.id)

            payload = {
                'name': self.name,
                'parents': [remote_directory.id]
            }

            if not self.mimeType:
                self.guess_mimeType()

            media = MediaFileUpload(self.path, 
                    mimetype = self.mimeType,
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
                # update the remote file properties with the response json
                remote_file.set_object(response)

                # set remote file as mirror of current file
                self.set_mirror(remote_file)

                # record sync time
                self.syncTime = datetime.now()
                remote_file.syncTime = self.syncTime
                log.say("Upload successful: ", self.path)
                return True
            else:
                log.error("Upload failed: ", response)
                return False

        elif self.is_dir():
            raise NotImplementedError("Directory upload not implemented")
            # create new dir
            # set mirror as self
            # set remote as self mirror
            # upload each child recursively


    def gdrive_update(self, remote_file):
        """ Update an existing G Drive file with a local file.
            @todo: update only bytes that changed.
            """

        if not self.exists:
            raise RuntimeError("Update failed, not found.", self)

        if not isinstance(remote_file, remote_fs.GDriveFS):
            raise TypeError("Target remote file must be remote_fs.GDriveFS type.", remote_file)

        if self.is_file():
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

        elif self.is_dir():
            raise NotImplementedError("Directory upload not implemented")
            # create new dir
            # set mirror as self
            # set remote as self mirror
            # upload each child recursively

