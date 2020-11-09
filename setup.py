from setuptools import setup, find_packages
import os
from os.path import expanduser
import glob

datadir = 'cryton/etc'
datafiles = [(datadir, list(glob.glob(os.path.join(datadir, '*'))))]

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(name='cryton',
      version='2020.4.1',
      description='Cryton - Attack scenario automation toolset',
      url='https://gitlab.ics.muni.cz/beast-public/cryton/cryton-core',
      author='Ivo Nutar, Jiri Raja, Andrej Tomci',
      author_email='nutar@ics.muni.cz, 469429@mail.muni.cz, 469192@mail.muni.cz',
      packages=find_packages(),
      python_requires='>3.8',
      install_requires=requirements,
      zip_safe=False,
      data_files=[(expanduser('~/.cryton/'), []),
                  (expanduser('~/.cryton/reports'), []),
                  (expanduser('~/.cryton/evidence'), []),
                  ('/etc/cryton/', []),
                  ('/etc/cryton', ['cryton/etc/logging_config.yaml']),
                  ('/etc/cryton', glob.glob('cryton/etc/config.*'))],
      entry_points={
          'console_scripts': [
              'cryton-manage=cryton.manage:main'
          ]
      },
      )
