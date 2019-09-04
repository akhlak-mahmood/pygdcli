import sys
import os

from datetime import datetime, date, time

DEBUG = 'Trace'
INFO = 'Info'
WARNING = 'WARNING'
ERROR = 'ERROR'
CRITICAL = 'CRITICAL'

_output = None
_max_level = None
_format = None
_log_errors = True
_loggable_levels = []
_levels = [DEBUG, INFO, WARNING, ERROR, CRITICAL]


def _write(text):
    global _output
    _output.write(text+'\n')
    _output.flush()

def _above_max_level(level):
    if level in _loggable_levels or level not in _levels:
        return True
    else:
        return False

def set_max_level(threshold):
    global _max_level, _levels, _loggable_levels
    _max_level = threshold
    if threshold not in _levels:
        raise ValueError("Unrecognized max level")

    for i in range(len(_levels)):
        if _levels[i] == _max_level:
            break
    _loggable_levels = _levels[i:]


def set_output(stream):
    global _output, _log_errors

    if isinstance(_output, str):
        if not os.path.isdir(os.path.dirname(stream)):
            os.makedirs(os.path.dirname(stream))

        try:
            _output = open(stream, 'a+')
        except IOError as e:
            raise IOError("Could not open {file}".format(file=e.filename))

        try:
            _output.write('')
            _output.flush()
        except AttributeError as e:
            raise IOError("Cannot write to {file}.".format(file=e.filename))

    else:
        try:
            stream.write('')
            stream.flush()
        except AttributeError:
            raise AttributeError("Provided stream object is invalid, must implement write and flush methods")
        except IOError:
            raise IOError("Cannot write to provided stream object")

        _output = stream

    if _log_errors:
        sys.stderr = _output

def set_format(format):
    global _format
    _format = format

def _log(log_level, text):
    global _format
    if _above_max_level(log_level):
        now = datetime.now()
        _write(_format.format(time=now.time(),
                    datetime=now,
                    date=date.today(),
                    level=log_level,
                    text=text
            ))

def _new(text):
    global _format, _max_level
    now = datetime.now()
    _write("\n"+_format.format(time=now.time(), datetime=now,
                    date=date.today(),
                    level=_max_level,
                    text=text
            ))

def _formatted(*text):
    if len(text) == 1:
        return text[0]
    else:
        fmt = text[0]
        args = []
        for i in range(len(text) - 1):
            args.append(text[i+1].__str__())

        if "{" in fmt and "}" in fmt:
            return fmt.format(*args)
        else:
            return fmt + " ".join(args)

def trace(*text):
    _log(DEBUG, _formatted(*text))

def say(*text):
    _log(INFO, _formatted(*text))

def warn(*text):
    _log(WARNING, _formatted(*text))

def error(*text):
    _log(ERROR, _formatted(*text))

def critical(*text):
    _log(CRITICAL, _formatted(*text))


if _max_level == None:
    set_max_level(INFO)

if _format is None:
    set_format('-- {level}:: {text}')

if _output is None:
    _output = sys.__stdout__

_new("Logging Started")
