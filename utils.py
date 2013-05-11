from functools import wraps

from fabric.api import settings, run, sudo, hide
from fabric.contrib.files import append, contains, sed

class DeferCommand(object):
    "Prepares a command to run at a later time."
    def __init__(self, cmd):
        self.cmd = cmd
        self.needs_to_execute = False
        self._ignore_runs = False

    def __call__(self, fn):
        """Decorates the given function to run the stored function after its execution.

        If a parent function is also decorated, it will only call after the parent function
        has finished:

            cleanup = DeferCommand(...)

            @cleanup
            def throw_trash():
                pass

            @cleanup
            def parent():
                throw_trash()
                # cleanup will get called here
        """
        self.needs_to_execute = True
        @wraps(fn)
        def wrapper(*args, **kwargs):
            old_value = self._ignore_runs
            self._ignore_runs = True
            result = fn(*args, **kwargs)
            self._ignore_runs = old_value
            self.run()
            return result
        return wrapper

    def run(self):
        if self.needs_to_execute and not self._ignore_runs:
            self.cmd()
        self.needs_to_execute = False

def silent(cmd, use_sudo=True):
    with settings(warn_only=True):
        return (sudo if use_sudo else run)(cmd).return_code

def ensure_line(filename, find_text, replace_text=None):
    "Inserts the given replace_text to a filename, or optionally replace the find_text."
    if replace_text is None:
        replace_text = find_text
    if silent('cat {0!r} | grep -q {1!r}'.format(filename, find_text), use_sudo=True) == 0:
        sed(filename, find_text, replace_text, use_sudo=True)
    else:
        append(filename, replace_text, use_sudo=True)

def trim_greeting(output):
    with hide('stdout'):
        motd_output = run('echo THEEOF')
        return output[motd_output.find('THEEOF'):]

OVERCLOCKING_MODES = dict(
    none=dict(
        arm_freq=700,
        core_freq=250,
        sdram_freq=400,
        over_voltage=0,
    ),
    modest=dict(
        arm_freq=800,
        core_freq=250,
        sdram_freq=400,
        over_voltage=0,
    ),
    medium=dict(
        arm_freq=900,
        core_freq=250,
        sdram_freq=450,
        over_voltage=2,
    ),
    high=dict(
        arm_freq=950,
        core_freq=250,
        sdram_freq=450,
        over_voltage=6,
    ),
    turbo=dict(
        arm_freq=1000,
        core_freq=500,
        sdram_freq=600,
        over_voltage=6,
    ),
)

def update_rpi_config(**parameters):
    for key, value in parameters.items():
        ensure_line('/boot/config.txt', r'#*{0}=.*'.format(key), '{0}={1}'.format(key, value))


