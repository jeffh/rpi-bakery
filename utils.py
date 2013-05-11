class DeferCommand(object):
    "Prepares a command to run at a later time."
    def __init__(self, cmd):
        self.cmd = cmd
        self.needs_to_execute = False

    def __call__(self, fn):
        self.needs_to_execute = True
        return fn

    def run(self):
        if self.needs_to_execute:
            self.cmd()
        self.needs_to_execute = False

def ensure_line(filename, find_text, replace_text=None):
    "Inserts the given replace_text to a filename, or optionally replace the find_text."
    if replace_text is None:
        replace_text = find_text
    if contains(filename, find_text, use_sudo=True):
        sed(filename, find_text, replace_text, use_sudo=True)
    else:
        append(filename, replace_text, use_sudo=True)

