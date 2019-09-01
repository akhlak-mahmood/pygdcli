import re
import json


class AttrDict(dict):
    """ Adds a convenient way to access dictionary items as properties """

    def __init__(self, d=None):
        if type(d) == dict:
            for k, v in d.items():
                self.__setattr__(k, v)

    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    def _legal_key(self, strg, search=re.compile(r'^[a-zA-Z_][a-zA-Z_0-9]*$').search):
        # key can't start with a digit, must be alphanumeric
        # unscore allowed
        return bool(search(strg))
    
    def __setitem__(self, key, value):
        # do not allow any key from dict's namespace
        if key in dir({}):
            raise KeyError(key)

        # key has to be string
        if type(key) != str:
            raise KeyError(key)

        if not self._legal_key(key):
            raise KeyError(key)

        super(AttrDict, self).__setitem__(key, value)

    def __dir__(self):
        return super().__dir__() + [str(k) for k in self.keys()]

    def save_json(self, json_file, compressed=False):
        with open(json_file, 'w+') as fp:
            if compressed:
                json.dump(self, fp, indent=None, separators=(',', ':'))
            else:
                json.dump(self, fp, indent=4)
        print(" -- Write OK:", json_file)

    def load_json(self, json_file):
        with open(json_file, 'r') as fp:
            d = json.load(fp)
        self.__init__(d)
        print(" -- Read OK:", json_file)

    def save(self, json_file):
        self.save_json(json_file)



def interactive(handler=None):
    import os
    import sys
    import traceback
    try:
        import readline
        readline.read_history_file('.pyhist')
    except:
        pass

    while True:
        cmd = input(">> ")
        if cmd.strip() in ["exit", "close", "quit", "shutdown", "exit()", "quit()", "shutdown()"]:
            break

        if cmd.strip() in ["cls", "CLS", "clscr", "clear"]:
            os.system("clear")
            continue

        cmd = cmd.strip()

        # if a command handler is specfied and it handled it, we are good
        if handler:
            try:
                if handler(cmd):
                    continue
            except Exception:
                print()
                traceback.print_exc(file=sys.stdout)
                print()
                continue

        # otherwise try pure python
        try:
            exec(cmd, globals())

        except (KeyboardInterrupt, SystemExit):
            print("[Keyboard Interrupt]")
            break

        except Exception:
            print()
            traceback.print_exc(file=sys.stdout)
            print()

def _do_cmp(f1, f2):
    bufsize = 1048576
    if os.path.getsize(f1) != os.path.getsize(f2):
        return False
    with open(f1, 'rb') as fp1, open(f2, 'rb') as fp2:
        while True:
            b1 = fp1.read(bufsize)
            b2 = fp2.read(bufsize)
            if b1 != b2:
                return False
            if not b1:
                return True

