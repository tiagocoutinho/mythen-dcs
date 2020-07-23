from mythendcs import Mythen, UDP_PORT, TCP_PORT, MythenError, COUNTER_BITS
from unittest import TestCase, TestSuite, TextTestRunner
import random
import time

class MythenDCSCoreTest(TestCase):
    def __init__(self, host, port, methodName='runTest'):
        super(MythenDCSCoreTest, self).__init__(methodName)
        self.mythen = Mythen(host, port)

    def runTest(self, result=None):
        raise NotImplementedError('You must implement it')

    def test_load_calib(self):
        self.mythen.settingsmode = 'HgCr'
        msg = 'Can not load HgCr calibration'
        self.assertEqual(self.mythen.settings, 'Highgain', msg)
        self.mythen.settingsmode = 'StdCu'
        msg = 'Can not load StdCu calibration'
        self.assertEqual(self.mythen.settings, 'Standard', msg)

    def test_acq(self, frames=10, inttime=1):
        self.mythen.frames = frames
        if inttime < 1:
            raise ValueError('The integration time should be greater than 1 '
                             'second to work with the test.')
        self.mythen.inttime = inttime
        self.mythen.start()
        msg = 'The acquisition did not start'
        self.assertEqual(self.mythen.status, 'RUNNING', msg)
        for i in range(frames):
            self.mythen.readout
        msg = 'The acquisition did not finish'
        self.assertEqual(self.mythen.status, 'ON', msg)
        #self.assertRaises(MythenError, self.mythendcs.readout)

    def test_readoutbits(self):
        for i in COUNTER_BITS:
            self.mythen.readoutbits = i
            msg = 'Error to set the readout bit to %s' % i
            self.assertEqual(self.mythen.readoutbits, i, msg)

    def test_stop_acq(self):
        self.mythen.frames = 10
        self.mythen.inttime = 1
        self.mythen.start()
        msg = 'The acquisition did not start'
        self.assertEqual(self.mythen.status, 'RUNNING', msg)
        time.sleep(random.random()*7)
        self.mythen.stop()
        msg = 'The acquisition did not stop'
        self.assertEqual(self.mythen.status, 'ON', msg)

if __name__ == '__main__':
    import argparse as ap

    port = ['UDP', 'TCP']
    parser = ap.ArgumentParser(description='Unittest for MythenDCS core.')
    parser.add_argument('host', type=str, nargs=1, help='Mythen IP')
    parser.add_argument('port', type=str, nargs=1, choices=port,
                        help='port UDP or TCP')

    args = parser.parse_args()

    if args.port[0] == port[0]:
        port = UDP_PORT
    else:
        port = TCP_PORT

    host = args.host[0]

    MythenTestSuite = TestSuite()
    MythenTestSuite.addTest(MythenDCSCoreTest(host, port, 'test_load_calib'))
    MythenTestSuite.addTest(MythenDCSCoreTest(host, port, 'test_acq'))
    MythenTestSuite.addTest(MythenDCSCoreTest(host, port, 'test_stop_acq'))
    MythenTestSuite.addTest(MythenDCSCoreTest(host, port, 'test_readoutbits'))

    runner = TextTestRunner()
    result = runner.run(MythenTestSuite)

    errors = len(result.errors)
    failures = len(result.failures)

    print('\n' * 2, '=' * 80)
    print('Results ')
    print('Error: ', errors)
    print('Failures: ', failures)
