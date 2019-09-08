Algorithm:
=====================================================================
A       = Local files
B       = Remote files
D/DB    = Database records
dB      = Remote changes
dA      = Local changes

Qmirror = file(item.path, type (B if item A else A)) or None
mirror  = db.calculate_mirror_from_path(item)
dbFile  = db.get_file(item.path, type of item)

proc item.same_signature(other):
    item.size       ==  other.size
    item.md5        ==  other.md5
    item.deleted    ==  other.deleted

// calculate dA
for each item in DB with type A:
    if not item.same_signature(dbFile):
        dA.add(item)
        [S9]
for each item in A not in DB:
        dA.add(item)

for each item in (A or dA or B or dB):
    if item in DB:
        // change, no change, delete
        if item.same_signature(dbFile):
            // no change
            pass
        if not item.same_signature(dbFile):
            // change, delete
            if Qmirror:
                // change in both A and B
                if item.same_signature(Qmirror):
                    // same change in both A and B
                    DB.update(item)
                else:
                    // conflict
                    resolve_conflict(item, mirror)
                    DB.update(item)
            else:
                // delete in only A or B
                if item.deleted():
                    mirror.remove()
                    DB.delete(item)
                    DB.delete(mirror)
                    [S8]
                else:
                    // change in only A or B
                    sync(item, mirror)
                    DB.update(item)
                    DB.update(mirror)
                    [S7,S9]
    else:
        // new file, new setup
        if Qmirror:
            // item in both A and B
            if item.same_signature(Qmirror):
                // same in both A and B
                DB.add(item)
                [S2]
            else:
                // different version in A and B
                resolve_conflict(item, mirror)
                DB.add(item)
                [S2]
        else:
            // new file
            item.upload_or_download(mirror)
            DB.add(item)
            [S3,S4,S5,S6]

[S1]

Scenerios:
=====================================================================
S1:
    "Both empty folder in local and remote, DB empty"
    no files in A, no files in B, no files in DB

S2:
    "Files both in local and remote, DB empty"
    files in A, files in B, no files in DB

S3:
    "Empty local, files in remote, DB empty"
    no files in A, files in B, no files in DB

S4:
    "Files in local, empty remote, DB empty"
    files in A, no files in B, no files in DB

S5:
    "New local file"
    file in A, not in DB

S6:
    "New remote file"
    file in B, not in DB

S7:
    "Delete in local"
    file in DB, not in A

S8:
    "Delete in remote"
    file in DB, delete event in dB

S9:
    "Local change"
    file in DB, file in A

S10:
    "Remote change"
    file in DB, update event in dB
