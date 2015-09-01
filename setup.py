from distutils.core import setup
from mythendcs import __version__
setup(
    name='MythenDCS',
    version=__version__,
    packages=['mythendcs'],
    scripts=['script/MythenDCS', 'test/test_mythendcs_core.py'],
    url='',
    license='',
    author='Roberto Homs Puron',
    author_email='rhoms@cells.com',
    description='Device server to control the MythenDCS1'
)
