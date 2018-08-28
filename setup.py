from setuptools import setup, find_packages

# The version is updated automatically with bumpversion
# Do not update manually
__version = '1.3.7'
long_description = 'Tango Device Server (DS) to have the remote control of '\
                   'the Mythen DCS1 detector.\n The DS implement the '\
                   'acquisition method and the live mode to acquire in real' \
                   'time. In addition it exports as attributes the '\
                   'configuration parameters.'
setup(
    name='MythenDCS',
    version=__version,
    packages=find_packages(),
    include_package_data=True,
    
    url='https://git.cells.es/controls/mythen',
    license = "GPL3",
    entry_points={
        'console_scripts': [
            'MythenDCS = mythendcs.server:main',
        ]
    author='Roberto Homs Puron',
    author_email='rhoms@cells.com',
    description='Device server to control the MythenDCS1',
    long_description=long_description,
    release='1',
    requires=['numpy (>=1.1)', 'PyTango (>=7.1)'],
    conflicts=[''],
    )


