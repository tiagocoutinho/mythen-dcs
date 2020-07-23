from setuptools import setup, find_packages

# The version is updated automatically with bumpversion
# Do not update manually
__version = '1.4.4'
long_description = 'Tango Device Server (DS) to have the remote control of '\
                   'the Mythen DCS1 detector.\n The DS implement the '\
                   'acquisition method and the live mode to acquire in real' \
                   'time. In addition it exports as attributes the '\
                   'configuration parameters.'

setup(
    name="MythenDCS",
    description="Device server to control the MythenDCS1",
    version=__version,
    author="Roberto J. Homs Puron",
    author_email="rhoms@cells.es",
    url="https://git.cells.es/controls/mythen",
    packages=find_packages(),
    package_data={},
    include_package_data=True,
    license="GPL3",
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: Python Software Foundation License',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Topic :: Communications',
        'Topic :: Software Development :: Libraries',
    ],
    entry_points={
        'console_scripts': [
            'MythenDCS = mythendcs.server:main'
        ]
    },
    requires=['numpy (>=1.1)', 'PyTango (>=7.1)'],
    conflicts=['']
)



