class ErrorNotFileSystemObject(TypeError):
    pass

class ErrorNotDriveFSObject(ErrorNotFileSystemObject):
    pass 

class ErrorNotLinuxFSObject(ErrorNotFileSystemObject):
    pass

class ErrorPathResolve(ValueError):
    pass

class ErrorTimeInvalid(ValueError):
    pass

class ErrorDirectionDetection(RuntimeError):
    pass 

class ErrorPathNotExists(FileExistsError):
    pass 

class ErrorParseResponseObject(RuntimeError):
    pass 

class ErrorIDNotSet(ValueError):
    pass

class ErrorNameNotSet(ValueError):
    pass 

class ErrorNotInDatabase(FileNotFoundError):
    pass 

class ErrorParentNotFound(ErrorPathResolve):
    pass 
