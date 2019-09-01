from . import log
from . import auth 

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
