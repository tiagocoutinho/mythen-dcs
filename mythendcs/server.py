import sys
from PyTango import Util, DevFailed
from .device import MythenDCSClass, MythenDCSDevice
from .__init__ import version

SERVER_NAME = 'MythenDCS'


def main():

    try:
        print(('Running MythenDCS version: {0}'.format(version)))
        # TODO use argparser
        util = Util(sys.argv)
        util.add_class(MythenDCSClass, MythenDCSDevice)
        U = Util.instance()
        U.server_init()
        U.server_run()

    except DevFailed as e:
        print('-------> Received a DevFailed exception:', e)
    except Exception as e:
        print('-------> An unforeseen exception occurred....', e)


if __name__ == '__main__':
    main()
