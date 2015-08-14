from distutils.core import setup

setup(
    name='MythenDCS',
    version='1.0',
    packages=['mythendcs'],
    scripts=['script/MythenDCS', 'test/test_mythendcs_core.py'],
    url='',
    license='',
    author='Roberto Homs Puron',
    author_email='rhoms@cells.com',
    description='Device server to control the MythenDCS1'
)
