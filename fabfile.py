import re
from StringIO import StringIO

from fabric.api import sudo, task, put, hide, reboot
from fabric.contrib.files import append, contains, sed, comment

from utils import DeferCommand, ensure_line, update_rpi_config, OVERCLOCKING_MODES, trim_greeting

apt_clean = DeferCommand(lambda: sudo('apt-get clean && apt-get autoremove -qy'))
requires_restart = DeferCommand(reboot)

def _cleanup():
    apt_clean.run()
    requires_restart.run()

cleanup = DeferCommand(_cleanup)

@task
def restart():
    "Restarts the machine."
    reboot()

@task
@requires_restart
def set_gpu_memory(mem_in_mb=16):
    """Sets the number of megabytes allocated for the GPU.

    Should probably be in powers of 2: 16, 32, 64, 128.

    """
    print " ~> GPU Memory:", mem_in_mb, "MB"
    update_rpi_config(gpu_mem=int(mem_in_mb))

@task
@requires_restart
def overclock(mode='modest'):
    """Programmatically set the overclocking modes.

    Available choices: none, modest, medium, high, turbo
    Defaults to none.

    """
    mode = str(mode).lower()
    parameters = OVERCLOCKING_MODES[mode]
    print " ~> Overclock:", mode
    for key, value in parameters.items():
        print "   ", key, "=", repr(value)
    update_rpi_config(**parameters)

@task
def remove_desktop_files():
    "Remove desktop Files bundled in the raspbian distro."
    sudo('rm -rf Desktop python_games; true')

@task
@apt_clean
def set_packages_from_list(filename):
    "Ensures the given filename of packages installed. This will uninstall packages that are not in the given file."
    with open(filename) as h:
        keep_pkgs = set(h.read().splitlines())
    with hide('output'):
        installed_pkgs = trim_greeting(sudo("dpkg --get-selections | grep -v 'deinstall$'"))
    installed_pkgs = re.split(r'[ \n\t\r]+', installed_pkgs)
    installed_pkgs = set(p.strip() for p in installed_pkgs) - set(['install'])
    pkgs_to_purge = installed_pkgs - keep_pkgs
    sudo('apt-get purge -qy {0}'.format(' '.join(pkgs_to_purge)))
    pkgs_to_install = keep_pkgs - installed_pkgs
    sudo('apt-get install -qy {0}'.format(' '.join(pkgs_to_install)))

@task
def set_swapsize(size=100, swappiness=1, cache_pressure=50):
    "Specifies the raspberry pi's swap size, usage, and swap file cache."
    if size > 0:
        sudo('echo "CONF_SWAPSIZE={0}" > /etc/dphys-swapfile'.format(size))
        sudo('dphys-swapfile setup')
        sudo('dphys-swapfile swapon')
    else:
        sudo('swapoff -a')

    ensure_line('/etc/sysctl.conf', 'vm.swappiness=[0-9]*', 'vm.swappiness={0}'.format(swappiness))
    ensure_line('/etc/sysctl.conf', 'vm.vfs_cache_pressure=[0-9]*', 'vm.vfs_cache_pressure={0}'.format(cache_pressure))

@task
@apt_clean
def replace_openssh_server_with_dropbear(allow_root=True, allow_passwords=True):
    """Installs dropbear to port 22. For recovery reasons, openssh will be moved to port 23.

    You'll need to manually remove openssh-server package:
        apt-get purge -y openssh-server

    """
    sudo("apt-get install -yq dropbear openssh-client")
    print '  -> Moving OpenSSH server to port 23, you will have to remove openssh-server manually'
    with settings(warn_only=True):
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
    "Updates all packages and upgrades the distro."
    sudo("apt-get -qy update && apt-get -qy dist-upgrade && apt-get -qy autoremove && apt-get -qy autoclean")

@task
@requires_restart
def optimize_mount():
    "Disables writing access timestamps to the file system."
    sudo("sed -i 's/defaults,noatime/defaults,noatime,nodiratime/g' /etc/fstab")

@task
@requires_restart
def disable_ipv6():
    "Disable IPv6."
    sudo('echo "net.ipv6.conf.all.disable_ipv6=1" > /etc/sysctl.d/disableipv6.conf')
    ensure_line("/etc/modprobe.d/blacklist", "blacklist ipv6")
    sudo("sed -i '/::/s%^%#%g' /etc/hosts")

@task
@requires_restart
def use_noop_scheduler():
    """Switches from deadline to noop scheduler of processes for the kernel.

    Noop minimizes CPU usage of the scheduler.

    """
    ensure_line('/boot/cmdline.txt', 'deadline', 'noop')

@task
def remove_extra_tty_and_gettys():
    "Remove extra terminals (tty) per session."
    comment('/etc/inittab', '[2-6]:23:respawn:/sbin/getty 38400 tty[2-6]', use_sudo=True)

@task
@requires_restart
def set_static_ip(ipaddr, netmask='255.255.255.0', network='192.168.1.0', gateway='192.168.1.1', broadcast='192.168.1.255'):
    "Sets the raspberry pi to use a static ip address."
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
@apt_clean
@requires_restart
def build_system(packages_filelist, static_ip=None, swap_size=512):
    "Builds the entire system."
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

