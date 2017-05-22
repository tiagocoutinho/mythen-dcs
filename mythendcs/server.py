import sys
from PyTango import Util, DevFailed
from .device import MythenDCSClass, MythenDCSDevice

SERVER_NAME = 'MythenDCS'

def main():

    try:
        # TODO use argparser
        util = Util(sys.argv)
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
