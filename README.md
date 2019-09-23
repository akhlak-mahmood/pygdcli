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
This will create a *settings.json* file.

- Next edit the settings file specifying your desired Google Drive sync directory. For example,
```json
{
"local_root_path": "Photos",
"remote_root_path": "/Photos",
"token_pickle": "token.pk",
"db_file": "db-photos.sqlite"
}
```
- Run the client again
```bash
~/pygdcli/gdcli settings.json
```
 A new browser window should open to authenticate the app and grant permissions to access your Drive files.

 *Please note that, the app has not been verified by Google yet, so you will have to choose to continue with the "unsafe" option during authetication.*

# Features
- You can sync multiple folders by specifying different root_paths and db_file.
- You can use multiple google accounts by specifying different token_pickle paths.

# Limitations
- Intial sync may take some time depending on the number of files you have.
- The app does not watch file changes, so run the client each time you need to sync.
- Files are downloaded to memory first, so file greater than your RAM size will fail to download.

# Dependencies
- pytz
- python-dateutil
- google-api-python-client
- google-auth-httplib2
- google-auth-oauthlib
- peewee

# License
GNU General Public License v3.0 (c) 2019 Akhlak Mahmood
