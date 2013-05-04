import re
from StringIO import StringIO

from fabric.api import sudo, task, put, hide, reboot
from fabric.contrib.files import append, contains, sed, comment

class _DeferCommand(object):
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

apt_clean = _DeferCommand(lambda: sudo('apt-get clean && apt-get autoremove -qy'))
requires_restart = _DeferCommand(reboot)

def _ensure_line(filename, find_text, replace_text=None):
    if replace_text is None:
        replace_text = find_text
    if contains(filename, find_text, use_sudo=True):
        sed(filename, find_text, replace_text, use_sudo=True)
    else:
        append(filename, replace_text, use_sudo=True)

@task
def cleanup():
    apt_clean.run()
    requires_restart.run()

@task
def remove_desktop_files():
    sudo('rm -rf Desktop python_games; true')

@task
@apt_clean
def set_packages_from_list(filename):
    with open(filename) as h:
        keep_pkgs = set(h.read().splitlines())
    with hide('output'):
        installed_pkgs = sudo("dpkg --get-selections | grep -v 'deinstall$'")
    installed_pkgs = re.split(r'[ \n\t\r]+', installed_pkgs)
    installed_pkgs = set(p.strip() for p in installed_pkgs) - set(['install'])
    pkgs_to_purge = installed_pkgs - keep_pkgs
    sudo('apt-get purge -qy {0}'.format(' '.join(pkgs_to_purge)))
    pkgs_to_install = keep_pkgs - installed_pkgs
    sudo('apt-get install -qy {0}'.format(' '.join(pkgs_to_install)))

@task
def set_swapsize(size=100, swappiness=1, cache_pressure=50):
    if size > 0:
        sudo('echo "CONF_SWAPSIZE={0}" > /etc/dphys-swapfile'.format(size))
        sudo('dphys-swapfile setup')
        sudo('dphys-swapfile swapon')
    else:
        sudo('swapoff -a')

    _ensure_line('/etc/sysctl.conf', 'vm.swappiness=[0-9]*', 'vm.swappiness={0}'.format(swappiness))
    _ensure_line('/etc/sysctl.conf', 'vm.vfs_cache_pressure=[0-9]*', 'vm.vfs_cache_pressure={0}'.format(cache_pressure))

@task
@apt_clean
def replace_openssh_server_with_dropbear(allow_root=True, allow_passwords=True):
    "http://blog.extremeshok.com/archives/1081"
    sudo("apt-get install -yq dropbear openssh-client")
    print '  -> Moving OpenSSH server to port 23, you will have to remove openssh-server manually'
    sed('/etc/ssh/sshd_config', 'Port [0-9]*', 'Port 23', use_sudo=True)
    sudo("service ssh restart")
    sed('/etc/default/dropbear', 'NO_START=[0-9]', 'NO_START=0', use_sudo=True)
    args = []
    if not allow_root:
        args.append('-w')
    if not allow_passwords:
        args.append('-s')
    sed('/etc/default/dropbear', 'DROPBEAR_EXTRA_ARGS=.*', 'DROPBEAR_EXTRA_ARGS="{0}"'.format(' '.join(args)), use_sudo=True)
    sudo("service dropbear start")
    #sudo("apt-get purge -yq openssh-server")

@task
@requires_restart
@apt_clean
def update_raspbian():
    "http://blog.extremeshok.com/archives/1081"
    sudo("apt-get -qy update && apt-get -qy dist-upgrade && apt-get -qy autoremove && apt-get -qy autoclean")

@task
@requires_restart
def optimize_mount():
    "http://blog.extremeshok.com/archives/1081"
    sudo("sed -i 's/defaults,noatime/defaults,noatime,nodiratime/g' /etc/fstab")

@task
@requires_restart
def disable_ipv6():
    "http://blog.extremeshok.com/archives/1081"
    sudo('echo "net.ipv6.conf.all.disable_ipv6=1" > /etc/sysctl.d/disableipv6.conf')
    _ensure_line("/etc/modprobe.d/blacklist", "blacklist ipv6")
    sudo("sed -i '/::/s%^%#%g' /etc/hosts")

@task
@requires_restart
def use_noop_scheduler():
    "http://blog.extremeshok.com/archives/1081"
    _ensure_line('/boot/cmdline.txt', 'deadline', 'noop')

@task
def remove_extra_tty_and_gettys():
    "http://blog.extremeshok.com/archives/1081"
    comment('/etc/inittab', '[2-6]:23:respawn:/sbin/getty 38400 tty[2-6]', use_sudo=True)


@task
@requires_restart
def set_static_ip(ipaddr, netmask='255.255.255.0', network='192.168.1.0', gateway='192.168.1.1', broadcast='192.168.1.255'):
    # backup interface
    sudo('cp -f /etc/network/interfaces /etc/network/interfaces.dhcp-backup')
    interface = """
auto lo

iface lo inet loopback
iface eth0 inet static

address {ipaddr}
netmask {netmask}
network {network}
broadcast {broadcast}
gateway {gateway}
""".format(ipaddr=ipaddr, netmask=netmask, network=network, gateway=gateway, broadcast=broadcast)

    tmp_file = StringIO(interface)
    put(tmp, '/etc/network/interfaces', use_sudo=True, mode=644)

@task
def build_system(packages_filelist, static_ip=None, swap_size=512):
    with open(packages_filelist) as h:
        h.read(1) # try to read file

    print '===> Updating Raspbian...'
    update_raspbian()
    requires_restart.run()
    print '===> Removing RPi files...'
    remove_desktop_files()
    print '===> Enforcing system packages...'
    set_packages_from_list(packages_filelist)
    print '===> Replacing OpenSSH server with dropbear ...'
    replace_openssh_server_with_dropbear()
    #print '===> disabling ipv6...'
    #disable_ipv6()
    if static_ip:
        print '===> Setting IP Address to {0}'.format(static_ip)
        set_static_ip(static_ip)

    print '===> Optimizing fs mount'
    optimize_mount()
    print '===> Switching kernel scheduler ...'
    use_noop_scheduler()
    print '===> Removing extra TTYs ...'
    remove_extra_tty_and_gettys()
    print '===> Setting swapsize to {0}MB ...'.format(swap_size)
    set_swapsize(size=swap_size)
    print '===> Cleaning up and rebooting ...'
    cleanup()

