RPI-Bakery
==========

A simple series of remote commands to run to set up a RaspberryPi_.

.. _RasberryPi: http://www.raspberrypi.org/

Install
-------

Use pip_ to setup::

    pip install -r requirements.txt

.. _pip: http://www.pip-installer.org/en/latest/


Usage
-----

Then you can use fabric::

    fab -l # see all the commands

You'll probably just want to use `build_system` task with one of the given
packages for a quick reset of your raspberry pi::

    fab -H pi@pi build_system:raspberrypi-default-packages.txt

Use a comma to specify a static IP::

    fab -H pi@pi build_system:raspberrypi-default-packages.txt,192.168.1.2

You can use the other txt file to remove most of the pre-installed packages::

    fab -H pi@pi build_system:raspberrypi-min-packages.txt

That's it!
