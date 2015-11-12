from distutils.core import setup
from mythendcs import __version__

setup(
    name='MythenDCS',
    version=__version__,
    packages=['mythendcs'],
    scripts=['script/MythenDCS', 'test/test_mythendcs_core.py'],
    url='https://gitcomputing.cells.es/controls/mythen',
    license='LGPL',
    author='Roberto Homs Puron',
    author_email='rhoms@cells.com',
    description='Device server to control the MythenDCS1',
    long_description='Tango Device Server to control the 1D Mythen DCS1',
    release='1',
    requires=['numpy (>=1.1)', 'PyTango (>=7.1)'],
    conflicts=[''],
    )


