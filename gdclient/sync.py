import os

from . import log 
from . import auth

class Sync:
    def __init__(self, scopes, credentials_file, token_file):
        self.scopes = scopes
        self.credentials_file = credentials_file
        self.token_file = token_file

        self.setup_auth()
        self.login()

    def setup_auth(self):
        auth.set_scopes(self.scopes)

    def login(self):
        auth.authenticate(self.credentials_file, self.token_file)

    def add(self):
        """ Add an item to sync queue """
        pass 

    def run(self):
        """ Process sync queue """
        pass 

