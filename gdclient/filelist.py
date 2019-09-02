import os
import io
import shutil
import mimetypes
from . import log
from . import auth 

from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

def list_latest_files():
    log.trace("Listing latest files")
    if auth.service is None:
        log.critical("Auth service not running, please autheticate first.")
        return None

    # Call the Drive v3 API
    results = auth.service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    log.say("File listing OK")

    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            print(u'{0} ({1})'.format(item['name'], item['id']))

    return items


## load items in root 
def get_dir_items(dir_file_obj, nextPageToken=None):
    log.trace("Getting root items")
    if nextPageToken:
        results = auth.service.files().list(
            q="'%s' in parents and trashed = false" %dir_file_obj['id'],
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=nextPageToken,
            pageSize=50).execute()
    else:
        results = auth.service.files().list(
            q="'%s' in parents and trashed = false" %dir_file_obj['id'],
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=50).execute()

    if 'nextPageToken' in results:
        log.warn("List trancated, pagination needed")

    return results


def get_root_dirs():
    log.trace("Getting root directories")
    root_items = get_dir_items({"id": "root"})
    root_dirs = []
    for f in root_items['files']:
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            root_dirs.append(f)

    return root_dirs


def change_directory(dirobj):
    log.trace("Listing directory", dirobj)
    return get_dir_items(dirobj)


def download_file(fileobj, download_path=None):
    file_id = fileobj['id']
    request = auth.service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print("Download %d%%." % int(status.progress() * 100))

    log.trace("Writing file ", fileobj['name'])

    fh.seek(0)
    with open(fileobj['name'], 'wb') as f:
        shutil.copyfileobj(fh, f, length=131072)

    log.say("Save OK ", fileobj['name'])


def upload_file(filepath, dirobj={'id': 'root'}):
    fileobj = {
        'name': os.path.basename(filepath),
        'parents': [dirobj['id']],
    }

    mimeType, encoding = mimetypes.guess_type(filepath)
    if mimeType:
        fileobj['mimeType'] = mimeType

    media = MediaFileUpload(filepath,
                mimetype=fileobj['mimeType'],
                chunksize=1024*1024,
                resumable=True)

    file = auth.service.files().create(body=fileobj,
                    media_body=media,
                    fields='id,mimeType,size')

    response = None

    while response is None:
      status, response = file.next_chunk()
      if status:
        print ("Uploaded %d%%." % int(status.progress() * 100))

    if file:
        print(filepath + " uploaded successfully")

    print ("Your sharable link: " + "https://drive.google.com/file/d/" + response.get('id')+'/view')
    return response
