from setuptools import setup, find_packages

# The version is updated automatically with bumpversion
# Do not update manually
__version = '1.3.3'

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
    }
    author='Roberto Homs Puron',
    author_email='rhoms@cells.com',
    description='Device server to control the MythenDCS1',
    long_description='Tango Device Server to control the 1D Mythen DCS1',
    release='1',
    requires=['numpy (>=1.1)', 'PyTango (>=7.1)'],
    conflicts=[''],
    )


