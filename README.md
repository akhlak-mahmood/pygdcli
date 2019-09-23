# PYGDCLI
Python CLI client to selectively sync Google Drive directories from Ubuntu terminal.
# Installation
- Clone this git repo
```bash
git clone https://github.com/akhlak-mahmood/pygdcli.git ~/pygdcli
```
- Install the dependencies.
```bash
pip install --upgrade pytz python-dateutil google-api-python-client google-auth-httplib2 google-auth-oauthlib peewee
```
- Navigate to your local Google Drive sync directory.
```bash
mkdir ~/GDrive
cd ~/GDrive
```  
- Run the client with a path for the settings file.
```bash
~/pygdcli/gdcli settings.json
```
This will create a *settings.json* file and let you autheticate the app and grant permissions to let it access your Drive files. *Please note that, the app has not been verified by Google yet, so you will have to choose to continue with the "unsafe" option during authetication.*

- Next edit the settings file specifying your desired Google Drive sync directory. For example,
```json
{
"token_pickle": "token.pickle",
"credentials_file": "credentials.json",
"local_root_path": "Photos",
"remote_root_path": "/Photos",
"db_file": "db.sqlite"
}
```
- Run the client again
```bash
~/pygdcli/gdcli settings.json
```
Intial sync may take some time depending the number of files you have. The app does not watch file changes, so run the above command each time you need to sync.

# Dependencies
- pytz
- python-dateutil
- google-api-python-client
- google-auth-httplib2
- google-auth-oauthlib
- peewee

# License
GNU General Public License v3.0 (c) Akhlak Mahmood 2019
Please see the included LICENSE file for details.
