from . import utils
from . import filelist

class RemoteResource:

	resObject = None

	def __init__(self, resObject):
		self.resObject = resObject
		self.name = self.set_attr('name')
		self.id = self.set_attr('id')
		self.mimeType = self.set_attr('mimeType')
		self.parents = self.set_attr('parents')
		self.path = None
		self.is_local = False

	def set_attr(self, key):
		if key in self.resObject:
			return self.resObject[key]
		else:
			return None


class RemoteDirectory(RemoteResource):

	def __init__(self, resObject):
		super.__init__(self, resObject)
		self.is_dir = True
		self.mimeType = 'application/vnd.google-apps.folder'
		self.children = []

	def list(self):
		for child in filelist(self.resObject):
			self.children.append(child)

	def download(self):
		for child in self.children:
			child.download()


class RemoteFile(Resource):
	def __init__(self, resObject):
		super.__init__(self, resObject)
		self.is_dir = False

	def download(self):
		filelist.download_file(self.resObject)

