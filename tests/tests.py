import unittest

import os
import json
import gdclient.database as db
from gdclient.errors import *
from gdclient.local_fs import LinuxFS
from gdclient.remote_fs import GDriveFS

def load_test_responses():
    with open('tests/test_response_parent.json', 'r') as fp:
        a = json.load(fp)

    with open('tests/test_response_subdir.json', 'r') as fp:
        b = json.load(fp)

    return a, b

class TestRemote(unittest.TestCase):

    def test_path_id(self):
        parent, subdir = load_test_responses()
        rf = GDriveFS()
        rf.set_path_id('/sync_dir', 'test_12345', True)

        self.assertIsNotNone(rf.path)
        self.assertTrue(rf.is_dir())
        self.assertTrue(rf.exists)
        self.assertEqual(rf.id, 'test_12345')
        self.assertEqual(rf.path, '/sync_dir')
        self.assertIsNotNone(rf.mimeType())

        # set a google doc response object and parent path
        sd = GDriveFS(parent.get('files')[0], rf.path)
        
        self.assertEqual(sd.path, '/sync_dir/Market')
        self.assertFalse(sd.is_dir())
        self.assertIn(rf.id, sd.parentIds)
        self.assertTrue(sd.exists)
        self.assertTrue(sd.is_google_doc)
        self.assertIsNotNone(sd.mimeType())

        # set a file response object and parent path
        sd = GDriveFS(parent.get('files')[1], rf.path)
        
        self.assertEqual(sd.path, '/sync_dir/download.pdf')
        self.assertFalse(sd.is_dir())
        self.assertIn(rf.id, sd.parentIds)
        self.assertTrue(sd.exists)
        self.assertFalse(sd.is_google_doc)
        self.assertIsNotNone(sd.mimeType())

        # set a directory response object and parent path
        sd = GDriveFS(parent.get('files')[3], rf.path)
        
        self.assertEqual(sd.path, '/sync_dir/Photos')
        self.assertTrue(sd.is_dir())
        self.assertIn(rf.id, sd.parentIds)
        self.assertTrue(sd.exists)
        self.assertEqual(sd.id, "12345_photo_folder")
        self.assertIsNotNone(sd.mimeType())

class TestLocal(unittest.TestCase):

    def test_local_file_properties(self):
        fp = LinuxFS("settings.json")
        self.assertIsNotNone(fp.path)
        self.assertIsNotNone(fp.name)
        self.assertIs(fp.is_dir(), False)
        self.assertFalse(fp.children)
        self.assertIs(fp.exists, True)
        self.assertGreater(fp.size(), 0)
        self.assertIsNotNone(fp.md5())
        self.assertIs(fp.is_file(), True)
        self.assertIsNotNone(fp.mimeType())
        with self.assertRaises(NotADirectoryError):
            fp.list_dir()

    def test_local_dir_properties(self):
        fp = LinuxFS("gdclient")
        fp.list_dir()
        self.assertIsNotNone(fp.path)
        self.assertIsNotNone(fp.name)
        self.assertTrue(fp.is_dir())
        self.assertTrue(fp.children)
        self.assertIs(fp.exists, True)
        self.assertIsInstance(fp.children[0], LinuxFS)
        self.assertIsNotNone(fp.mimeType())

class TestDatabase(unittest.TestCase):
    test_database = 'test_database.sqlite'
    remote_path = '/sync_dir'

    def setUp(self):
        db.connect(self.test_database, self.remote_path)
        fp = LinuxFS("settings.json")
        db.add(fp)
        dp = LinuxFS("gdclient")
        db.add(dp)

        parent, subdir = load_test_responses()
        rr = GDriveFS()
        rr.set_path_id('/sync_dir', 'test_12345', True)
        db.add(rr)
        rf = GDriveFS(parent.get('files')[1], rr.path)
        db.add(rf)
        rd = GDriveFS(parent.get('files')[3], rr.path)
        db.add(rd)
        rdf = GDriveFS(subdir.get('files')[1], rd.path)
        db.add(rdf)

    def tearDown(self):
        db.close()

        if os.path.isfile(self.test_database):
            os.remove(self.test_database)

    def test_connect(self):
        if not db._db.is_closed():
            db.close()

        if os.path.isfile(self.test_database):
            os.remove(self.test_database)

        self.assertFalse(os.path.isfile(self.test_database))

        with self.assertRaises(ValueError):
            db.connect(self.test_database, None)

        db.connect(self.test_database, self.remote_path)
        self.assertFalse(db._db.is_closed())
        self.assertTrue(db.is_empty())

    def test_local_conversion(self):
        fp = LinuxFS("settings.json")
        dbObj = db._db_object_from_file(fp)

        self.assertIsInstance(dbObj, db.File)
        self.assertEqual(fp.path, dbObj.path)
        self.assertIsNotNone(dbObj.is_dir)
        self.assertEqual(dbObj.is_dir, fp.is_dir())
        self.assertIsNotNone(dbObj.name)
        self.assertEqual(dbObj.name, fp.name)
        self.assertIsNotNone(dbObj.id_str)
        self.assertEqual(dbObj.md5, fp.md5())


        fp2 = db._file_object_from_db(dbObj)

        self.assertIsInstance(fp2, LinuxFS)
        self.assertEqual(fp2.path, fp.path)
        self.assertIsNotNone(fp2.name)
        self.assertIsNotNone(fp2.id)
        self.assertIsNotNone(fp2.is_dir())
        self.assertIsNotNone(fp2.md5())
        self.assertIsNotNone(fp2.size())

    def test_local_dir_conversion(self):
        fp = LinuxFS("gdclient")

        dbObj = db._db_object_from_file(fp)

        self.assertIsInstance(dbObj, db.File)
        self.assertEqual(fp.path, dbObj.path)
        self.assertIsNotNone(dbObj.is_dir)
        self.assertEqual(dbObj.is_dir, fp.is_dir())
        self.assertIsNotNone(dbObj.name)
        self.assertEqual(dbObj.name, fp.name)
        self.assertIsNotNone(dbObj.id_str)

        fp2 = db._file_object_from_db(dbObj)

        self.assertIsInstance(fp2, LinuxFS)
        self.assertEqual(fp2.path, fp.path)
        self.assertIsNotNone(fp2.name)
        self.assertIsNotNone(fp2.id)
        self.assertIsNotNone(fp2.is_dir())

    def test_file_exists(self):
        fp = LinuxFS("settings.json")
        dp = LinuxFS("gdclient")
        rr = GDriveFS()
        rr.set_path_id('/sync_dir', 'test_12345', True)
        parent, subdir = load_test_responses()
        rf = GDriveFS(parent.get('files')[1], rr.path)
        rd = GDriveFS(parent.get('files')[3], rr.path)
        rdf = GDriveFS(subdir.get('files')[1], rd.path)
        self.assertTrue(db.file_exists(fp))
        self.assertTrue(db.file_exists(dp))
        self.assertTrue(db.file_exists(rr))
        self.assertTrue(db.file_exists(rf))
        self.assertTrue(db.file_exists(rd))
        self.assertTrue(db.file_exists(rdf))

        ret = db.get_file_by_id(rr.id)
        self.assertEqual(ret.path, rr.path)

    def test_update_status(self):
        ret = db.get_file_by_id('test_12345')
        db.update_status(ret, db.Status.synced)

        row = db.get_row_by_id('test_12345')
        self.assertEqual(row.status, db.Status.synced)


    def test_find_parent(self):
        child = db.get_row_by_id('test_id_1234SVdJZmdZLWxMcUk')
        parent = db._find_db_object_parent_as_file(child)
        self.assertEqual(parent.path, "/sync_dir/Photos")
        self.assertEqual(parent.id, "12345_photo_folder")
        grandparent = db._find_db_object_parent_as_file(parent)
        self.assertEqual(grandparent.id, "test_12345")

    def test_get_mirror(self):
        fp = LinuxFS("settings.json")
        dp = LinuxFS("gdclient")
        rr = GDriveFS()
        rr.set_path_id('/sync_dir', 'test_12345', True)
        parent, subdir = load_test_responses()
        rf = GDriveFS(parent.get('files')[1], rr.path)
        rd = GDriveFS(parent.get('files')[3], rr.path)
        rdf = GDriveFS(subdir.get('files')[1], rd.path)

        mirror = db.get_mirror(fp)
        self.assertEqual(mirror.path, '/sync_dir/settings.json')
        self.assertTrue(mirror.is_file())
        self.assertIn(rr.id, mirror.parentIds)
        self.assertFalse(mirror.exists)
        self.assertIsInstance(mirror, GDriveFS)

        mirror = db.get_mirror(dp)
        self.assertEqual(mirror.path, '/sync_dir/gdclient')
        self.assertTrue(mirror.is_dir())
        self.assertIn(rr.id, mirror.parentIds)
        self.assertFalse(mirror.exists)
        self.assertIsInstance(mirror, GDriveFS)

        mirror = db.get_mirror(rr)
        self.assertEqual(mirror.path, '.')
        self.assertTrue(mirror.is_dir())
        self.assertTrue(mirror.exists)
        self.assertIsInstance(mirror, LinuxFS)

        mirror = db.get_mirror(rd)
        self.assertEqual(mirror.path, 'Photos')
        self.assertTrue(mirror.is_dir())
        self.assertIsInstance(mirror, LinuxFS)

        mirror = db.get_mirror(rdf)
        self.assertEqual(mirror.path, 'Photos/Sample Photo (5).JPG')
        self.assertTrue(mirror.is_file())
        self.assertIsInstance(mirror, LinuxFS)

        fp = LinuxFS(".")
        self.assertTrue(db.mirror_exists(fp))

if __name__ == '__main__':
    unittest.main()
