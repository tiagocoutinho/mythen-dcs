from setuptools import setup, find_packages

# The version is updated automatically with bumpversion
# Do not update manually
__version = '1.4.4'
long_description = 'Tango Device Server (DS) to have the remote control of '\
                   'the Mythen DCS1 detector.\n The DS implement the '\
                   'acquisition method and the live mode to acquire in real' \
                   'time. In addition it exports as attributes the '\
                   'configuration parameters.'

extras_require = {
    "tango" : ["PyTango>=7.1"],
    "simulator": ["sinstruments>=1.1", "gevent"],
    "lima": ["lima-toolbox>=1", "beautifultable>=1", "click"],
}
extras_require["all"] = list(
    set.union(*(set(i) for i in extras_require.values()))
)

setup(
    name="MythenDCS",
    description="Device server to control the MythenDCS 1 and 4",
    version=__version,
    author="Roberto J. Homs Puron",
    author_email="rhoms@cells.es",
    url="https://git.cells.es/controls/mythen",
    packages=find_packages(),
    package_data={},
    include_package_data=True,
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 3',
        'Topic :: Communications',
        'Topic :: Software Development :: Libraries',
    ],
    entry_points={
        'console_scripts': [
            'MythenDCS = mythendcs.server:main [tango]'
        ],
        "Lima_camera": [
            "MythenDCS = mythendcs.lima.camera [lima]"
        ],
        "Lima_tango_camera": [
            "MythenDCS = mythendcs.lima.tango [lima]"
        ],
        "limatb.cli.camera": [
            'MythenDCS = mythendcs.lima.cli:mythendcs [lima]'
        ],
        "limatb.cli.camera.scan": [
            "MythenDCS = mythendcs.lima.cli:scan [lima]"
        ],
    },
    python_requires='>=3.5',
    install_requires=['numpy'],
    extras_require=extras_require
)
