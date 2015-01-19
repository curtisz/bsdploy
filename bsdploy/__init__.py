from os import path
import argparse
import logging
import sys


log = logging.getLogger("bsdploy")


# register our own library and roles paths into ansible
bsdploy_path = path.abspath(path.dirname(__file__))

ansible_paths = dict(
    roles=[path.join(bsdploy_path, 'roles')],
    library=[path.join(bsdploy_path, 'library')])

virtualbox_defaults = {
    'vm-ostype': 'FreeBSD_64',
    'vm-memory': '2048',
    'vm-accelerate3d': 'off',
    'vm-acpi': 'on',
    'vm-rtcuseutc': 'on',
    'vm-boot1': 'disk',
    'vm-boot2': 'dvd',
}

ez_instance_defaults = {
    'ansible_python_interpreter': '/usr/local/bin/python2.7',
    'fabric-shell': '/bin/sh -c',
}


class PloyBootstrapCmd(object):
    def __init__(self, ctrl):
        self.ctrl = ctrl

    def __call__(self, argv, help):
        """Bootstrap a jailhost that's been booted into MFSBsd."""
        parser = argparse.ArgumentParser(
            prog="%s bootstrap" % self.ctrl.progname,
            description=help)
        masters = dict((master.id, master) for master in self.ctrl.get_masters('ezjail_admin'))
        parser.add_argument(
            "master",
            nargs='?' if len(masters) == 1 else 1,
            metavar="master",
            help="Name of the jailhost from the config.",
            choices=masters,
            default=masters.keys()[0] if len(masters) == 1 else None)
        parser.add_argument(
            "-y", "--yes", action="store_true",
            help="Answer yes to all questions.")
        args = parser.parse_args(argv)
        master = args.master if len(masters) == 1 else args.master[0]
        instance = self.ctrl.instances[master]
        instance.hooks.before_bsdploy_bootstrap(instance)
        instance.do('bootstrap', **{'bootstrap-yes': args.yes})
        instance.hooks.after_bsdploy_bootstrap(instance)


def augment_instance(instance):
    from ploy_ansible import get_playbooks_directory, has_playbook

    if instance.master.sectiongroupname == ('vb-instance'):
        for key, value in virtualbox_defaults.items():
            instance.config.setdefault(key, value)

    if not instance.master.sectiongroupname.startswith('ez-'):
        return

    for key, value in ez_instance_defaults.items():
        instance.config.setdefault(key, value)

    if 'fabfile' not in instance.config:
        playbooks_directory = get_playbooks_directory(instance.master.main_config)
        fabfile = path.join(playbooks_directory, instance.uid, 'fabfile.py')
        if path.exists(fabfile):
            instance.config['fabfile'] = fabfile

    if instance.master.instance is instance:
        # for hosts
        if 'fabfile' not in instance.config:
            bootstrap_type = instance.config.get('bootstrap', 'mfsbsd')
            fabfile = path.join(bsdploy_path, 'fabfile_%s.py' % bootstrap_type)
            instance.config['fabfile'] = fabfile
        if not path.exists(instance.config['fabfile']):
            log.error("The fabfile '%s' for instance '%s' doesn't exist." % (
                instance.config['fabfile'], instance.uid))
            sys.exit(1)
        if not has_playbook(instance):
            instance.config['roles'] = 'jails_host'
        if 'fingerprint' not in instance.config:
            host_defined_path = instance.config.get('bootstrap-files')
            ploy_conf_path = instance.master.main_config.path
            if host_defined_path is None:
                bootstrap_path = path.join(ploy_conf_path, '..', 'bootstrap-files')
            else:
                bootstrap_path = path.join(ploy_conf_path, host_defined_path)
            ssh_key = path.abspath(path.join(bootstrap_path, 'ssh_host_rsa_key.pub'))
            if path.exists(ssh_key):
                instance.config['fingerprint'] = ssh_key
    else:
        # for jails
        instance.config.setdefault('startup_script', path.join(
            bsdploy_path, 'startup-ansible-jail.sh'))
        instance.config.setdefault('flavour', 'bsdploy_base')


def get_commands(ctrl):
    return [('bootstrap', PloyBootstrapCmd(ctrl))]


plugin = dict(
    augment_instance=augment_instance,
    get_commands=get_commands)
