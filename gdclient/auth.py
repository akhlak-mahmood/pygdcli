import os
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from . import log

_scopes = ['https://www.googleapis.com/auth/drive.metadata.readonly']
service = None 

def set_scopes(scope_items):
    global _scopes, _token_pickle

    if isinstance(scope_items, str):
        _scopes = [scope_items]
    else:
        _scopes = scope_items
    log.trace("Set new scopes ", _scopes)

def update_scopes(scope_items, _token_pickle):
    set_scopes(scope_items)
    # if scope is changed, re-authentication needed
    if os.path.isfile(_token_pickle):
        os.remove(_token_pickle)
        log.trace("Remove ", _token_pickle)

def authenticate(credentials_file, _token_pickle):
    global _scopes, service

    if len(_scopes) == 0:
        raise ValueError("Scopes not set, please set scopes first")

    creds = None 
    if os.path.exists(_token_pickle):
        with open(_token_pickle, 'rb') as token:
            creds = pickle.load(token)
        log.trace("Load token OK ", _token_pickle)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.trace("Token expired")
            try:
                log.trace("Refreshing auth token")
                creds.refresh(Request())
            except:
                log.critical("Failed refresh auth token")
                raise
            else:
                log.trace("Auth token refresh OK")
        else:
            log.say("No saved token found")
            try:
                log.trace("Creating flow object for login")
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, _scopes)
            except:
                log.critical("Failed flow object creation")
                raise
            else:
                log.trace("Flow creation OK")

            try:
                log.say("Staring local server for login")
                creds = flow.run_local_server(port=0)
            except:
                log.critical("Failed local server creation for login")
                raise
            else:
                log.trace("Local server start OK")

        # Save the credentials for the next run
        with open(_token_pickle, 'wb') as token:
            pickle.dump(creds, token)

        log.trace("Write ", _token_pickle, "OK")

    else:
        log.trace("Token OK")

    try:
        log.trace("Building API service with token")
        service = build('drive', 'v3', credentials=creds)
    except:
        log.critical("Failed building API service")
        raise
    else:
        log.trace("API service build OK")


