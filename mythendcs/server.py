from PyTango import Util, DevFailed
import sys
from mythendcs.device import MythenDCSClass, MythenDCSDevice
from mythendcs import __version__

SERVER_NAME = 'MythenDCS'

def run(args=None):
    print ('Device Server Version: %s' % __version__)

    try:
        if not args:
            args = sys.argv[1:]
            args = [SERVER_NAME] + list(args)
        util = Util(args)
        util.add_class(MythenDCSClass, MythenDCSDevice)
        U = Util.instance()
        U.server_init()
        U.server_run()

    except DevFailed, e:
        print '-------> Received a DevFailed exception:', e
    except Exception, e:
        print '-------> An unforeseen exception occurred....', e

if __name__ == '__main__':
    run()
