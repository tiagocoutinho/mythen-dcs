import socket
import struct
import functools
import threading
import contextlib

import numpy as np

COUNTER_BITS = [4, 8, 16, 24]

SETTINGS_MODES = ['StdCu', 'StdMo', 'HgCr', 'HgCu', 'FastCu', 'FastMo']

TCP_PORT = 1031
UDP_PORT = 1030

TCP = socket.SOCK_STREAM
UDP = socket.SOCK_DGRAM

ERR_MYTHEN_COMM_LENGTH = -40
ERR_MYTHEN_COMM_TIMEOUT = -41
ERR_MYTHEN_READOUT = -42
ERR_MYTHEN_SETTINGS = -43
ERR_MYTHEN_BAD_PARAMETER = -44

ERRORS = {
    -1: 'Unknown command',
    -2: 'Invalid argument',
    -3: 'Unknown settings',
    -4: 'Out of memory',
    -5: 'Module calibration files not found',
    -6: 'Readout failed',
    -7: 'Acquisition not finished',
    -8: 'Failure while reading temperature and humidity sensor',
    -9: 'Invalid license key',
    -10: 'Flat field not found',
    -11: 'Bad channel file not found',
    -12: 'Energy calibration not found',
    -13: 'Noise file not found',
    -14: 'Trim bit file not found',
    -15: 'Invalid format of the flat field file',
    -16: 'Invalid format of the bad channel file',
    -17: 'Invalid format of the energy calibration file',
    -18: 'Invalid format of the noise file',
    -19: 'Invalid format of the trim bit file',
    -20: 'Version file not found',
    -21: 'Invalid format of the version file',
    -22: 'Gain calibration file not found',
    -23: 'Invalid format of the gain calibration file',
    -24: 'Dead time file not found',
    -25: 'Invalid format of the dead time file',
    -26: 'High voltage file not found',
    -27: 'Invalid format of high voltage file',
    -28: 'Energy threshold relation file not found',
    -29: 'Invalid format of the energy threshold relation file',
    -30: 'Could not create log file',
    -31: 'Could not close log file',
    -32: 'Could not read log file',
    -50: 'No modules connected',
    -51: 'Error during module communication',
    -52: 'DCS initialization failed',
    -53: 'Could not store customer flat-field',
    ERR_MYTHEN_COMM_LENGTH: 'Error with the communication, the response size is greater than the default.',
    ERR_MYTHEN_COMM_TIMEOUT:'Error timed out, the device did not respond.',
    ERR_MYTHEN_READOUT: 'Error with the readout command.',
    ERR_MYTHEN_SETTINGS: 'Return and unknown settings code ({0}).',
    ERR_MYTHEN_BAD_PARAMETER: 'Bad parameter.'
}


class MythenError(Exception):
    def __init__(self, value, *args):
        self.errcode = value
        self.args = args

    def __str__(self):
        return "Error {}: {}".format(self.errcode, self._get_error_msg())

    def _get_error_msg(self):
        msg = ERRORS.get(self.errcode, "Unknown error code")
        return msg.format(*self.args)

    def __repr__(self):
        return '{}({}, {!r})'.format(
            type(self).__name__, self.errcode, self._get_error_msg()
        )


TRIGGER_TYPES = ['INTERNAL', 'EXTERNAL_TRIGGER_MULTI',
                 'EXTERNAL_TRIGGER_START', ]


def ensure_connection(f):

    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        just_connected = False
        if self.socket is None:
            self.connect()
            just_connected =True
        if self.kind == UDP or just_connected:
            return f(self, *args, **kwargs)
        try:
            result = f(self, *args, **kwargs)
            if result is b'':
                raise ConnectionError('remote end disconnected')
            return result
        except socket.timeout:
            self.disconnect()
            raise
        except OSError:
            self.connect()
            return f(self, *args, **kwargs)
    return wrapper


@contextlib.contextmanager
def guard_timeout(connection, timeout):
    if timeout == -1:
        yield
    else:
        prev_timeout = connection.socket.gettimeout()
        connection.socket.settimeout(timeout)
        try:
            yield
        finally:
            if connection.socket:
                connection.socket.settimeout(prev_timeout)


class Connection:
    """Communication channel"""

    def __init__(self, host, port, timeout=None, kind=None):
        self.host = host
        self.port  = port
        self.timeout = timeout
        self.kind = (UDP if port == UDP_PORT else TCP) if kind is None else kind
        self.socket = None
        self.fobj = None
        self.lock = threading.Lock()

    def __del__(self):
        self.disconnect()

    def __repr__(self):
        conn = "connected" if self.socket else "pending"
        kind = 'UDP' if self.kind == UDP else 'TCP'
        return "<{} {} {}>".format(kind, conn, (self.host, self.port))

    def connect(self):
        self.disconnect()
        sock = socket.socket(socket.AF_INET, type=self.kind)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self.fobj = sock.makefile("rwb", buffering=0)
        self.socket = sock

    def disconnect(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
            self.fobj = None

    def _read_exactly_into(self, buff):
        try:
            size = buff.nbytes
        except AttributeError:
            size = len(buff)
        offset, view = 0, memoryview(buff)
        while offset < size:
            offset += self.socket.recv_into(view[offset:])
        return buff

    @ensure_connection
    def write(self, data):
        self.fobj.write(data)

    @ensure_connection
    def read(self, size, timeout=-1):
        with guard_timeout(self, timeout):
            with self.lock:
                return self.fobj.read(size)

    @ensure_connection
    def read_exactly_into(self, buff, timeout=-1):
        with guard_timeout(self, timeout):
            with self.lock:
                return self._read_exactly_into(buff)

    @ensure_connection
    def write_read(self, data, size, timeout=-1):
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            with self.lock:
                return self.fobj.read(size)

    @ensure_connection
    def write_read_exactly_into(self, data, buff, timeout=-1):
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            with self.lock:
                self._read_exactly_into(buff)


def to_int(d):
    return struct.unpack_from("<i", d)[0]


def to_long_long(d):
    return struct.unpack_from("<q", d)[0]


def to_float(d):
    return struct.unpack_from("<f", d)[0]


to_int_list = functools.partial(np.frombuffer, dtype="<i4")


class Mythen:
    """
    Class to control the Mythen. Exported API:

    """
    MAX_BUFF_SIZE_MODULE = 10000
    MAX_CHANNELS = 1280
    MASK_RUNNING = 1  # Bit 0
    MASK_WAIT_TRIGGER = 1 << 3  # Bit 3
    MASK_FIFO_EMPTY = 1 << 16  # Bit 16

    def __init__(self, connection, nmod=1):
        """
        :param connection
        :param nmod: Number of modules
        """
        self.connection = connection
        self.buff = nmod * self.MAX_BUFF_SIZE_MODULE
        self.nchannels = nmod * self.MAX_CHANNELS
        self.frames = 1
        self.triggermode = False
        self.gatemode = False
        self.inputhigh = True
        self.outputhigh = True
        self.continuoustrigger = False

    def _send_msg(self, cmd):
        try:
            self.connection.write(cmd.encode() if isinstance(cmd, str) else cmd)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    def _receive_msg(self):
        try:
            return self.connection.read(self.buff)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    # ------------------------------------------------------------------
    #   Commands
    # ------------------------------------------------------------------
    def command(self, cmd, timeout=None):
        """
        Method to send command to Mythen. It verifies if there are errors.
        :param cmd: Command
        :return: Answer
        """
        cmd = cmd.encode() if isinstance(cmd, str) else cmd
        try:
            raw_value = self.connection.write_read(cmd, self.buff, timeout=timeout)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

        # sizeof(int)
        if len(raw_value) == 4:
            value = to_int(raw_value)
            if value < 0:
                raise MythenError(value)
        return raw_value

    def start(self):
        """
        :return: None
        """
        self.command('-start')

    def stop(self):
        """
        :return: None
        """
        self.command('-stop')

    def reset(self):
        """
        :return: None
        """
        # takes 2s + 0.5s per module: make sure the timeout is setup properly
        self.command('-reset', timeout=5)
        self._frames = 1

    def autosettings(self, value):
        """
        :param value: Energy threshold in keV
        :return:
        """
        if value <= 0:
            raise ValueError('The value should be greater than 0')
        self.command('-autosettings %f' % value)

    # ------------------------------------------------------------------
    #   Bad Channels
    # ------------------------------------------------------------------
    @property
    def badchn(self):
        """
        :return: Numpy array with the bad channels defined in the hardware.
        """
        raw_value = self.command('-get badchannels')
        values = to_int_list(raw_value)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    # ------------------------------------------------------------------
    #   Bad Channels Interpolation
    # ------------------------------------------------------------------
    @property
    def badchnintrpl(self):
        """
        :return: State of the bad channels interpolation.
        """
        raw_value = self.command('-get badchannelinterpolation')
        value = to_int(raw_value)
        return bool(value)

    @badchnintrpl.setter
    def badchnintrpl(self, value):
        """
        :param value: Boolean to activated/deactivated the bad channel
        interpolation.
        :return:
        """
        if type(value) != bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-badchannelinterpolation %d' % int(value))

    # ------------------------------------------------------------------
    #   Channels Flat Field Configuration
    # ------------------------------------------------------------------
    @property
    def flatfieldconf(self):
        """
        :return: Numpy array with the flat field value per each channels.
        """
        raw_value = self.command('-get flatfield')
        values = to_int_list(raw_value)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    # ------------------------------------------------------------------
    #   Flat Field Correction
    # ------------------------------------------------------------------
    @property
    def flatfield(self):
        """
        :return: State of the flat field correction.
        """
        raw_value = self.command('-get flatfieldcorrection')
        value = to_int(raw_value)
        return bool(value)

    @flatfield.setter
    def flatfield(self, value):
        """
        :param value: Boolean to activated/deactivated the flat field
        correction.
        :return:
        """
        if type(value) != bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-flatfieldcorrection %d' % int(value))

    # ------------------------------------------------------------------
    #   Frames
    # ------------------------------------------------------------------
    @property
    def frames(self):
        """
        :return: Number of frames.
        """
        return self._frames

    @frames.setter
    def frames(self, value):
        """
        :param value: Number of frames per acquisition.
        :return:
        """
        self.command('-frames %d' % value)
        self._frames = value

    # ------------------------------------------------------------------
    #   Integration Time
    # ------------------------------------------------------------------
    @property
    def inttime(self):
        """
        :return: Integration time in seconds.
        """
        raw_value = self.command('-get time')
        value = to_long_long(raw_value)
        value *= 100e-9  # Time in seconds
        return value

    @inttime.setter
    def inttime(self, value):
        """
        :param value: Integration time in seconds
        :return:
        """
        # Exposure value in units of 100ns.
        ntimes = int(value / 100e-9)
        self.command('-time %d' % ntimes)

    # ------------------------------------------------------------------
    #   M
    # ------------------------------------------------------------------

    def get_active_modules(self):
        raw_value = self.command('-get nmodules')
        value = to_int(raw_value)
        return value

    def set_module(self, value):
        if value not in list(range(self.nmod)):
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-module %d' % value)

    # ------------------------------------------------------------------
    #   Settings
    # ------------------------------------------------------------------
    @property
    def settings(self):
        """
        :return: String with the current settings: Standard, Highgain or Fast.
        """
        raw_value = self.command('-get settings')
        value = to_int(raw_value)
        if value == 0:
            result = 'Standard'
        elif value == 1:
            result = 'Highgain'
        elif value == 2:
            result = 'Fast'
        elif value == 3:
            result = 'Unknown'
        else:
            raise MythenError(ERR_MYTHEN_SETTINGS, value)
        return result

    # ------------------------------------------------------------------
    #   Settings Mode
    # ------------------------------------------------------------------
    @property
    def settingsmode(self):
        """
        :return: String with the current setting mode.
        """
        raw = self.command('-get settingsmode').decode()
        value = raw
        if 'auto' not in raw:
            value = (raw.split()[1])
        value = value.split('\x00')[0]
        return value

    @settingsmode.setter
    def settingsmode(self, value):
        """
        :param value: String with the setting mode: StdCu, StdMo, HgCr, HgCu,
        FastCu and FastMo.
        :return:
        """
        if value not in SETTINGS_MODES:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-settings %s' % value)

    # ------------------------------------------------------------------
    #   Status
    # ------------------------------------------------------------------
    @property
    def status(self):
        """
        :return: Return the status of the Mythen: On, Running or Wait Trigger.
        """
        raw_value = self.command('-get status')
        value = to_int(raw_value)
        if value & self.MASK_RUNNING:
            state = 'RUNNING'
        else:
            state = 'ON'
        return state

    # ------------------------------------------------------------------
    #   waitingtrigger
    # ------------------------------------------------------------------
    @property
    def waitingtrigger(self):
        """
        :return: Return the status of the Mythen: On, Running or Wait Trigger.
        """
        raw_value = self.command('-get status')
        value = to_int(raw_value)
        return bool(value & self.MASK_WAIT_TRIGGER)

    # ------------------------------------------------------------------
    #   fifoempty
    # ------------------------------------------------------------------
    @property
    def fifoempty(self):
        """
        :return: Return the status of the Mythen: On, Running or Wait Trigger.
        """
        raw_value = self.command('-get status')
        value = to_int(raw_value)
        return bool(value & self.MASK_FIFO_EMPTY)

    # ------------------------------------------------------------------
    #   running
    # ------------------------------------------------------------------
    @property
    def running(self):
        """
        :return: Return the status of the Mythen: On, Running or Wait Trigger.
        """
        raw_value = self.command('-get status')
        value = to_int(raw_value)
        return bool(value & self.MASK_RUNNING)

    # ------------------------------------------------------------------
    #   Rate
    # ------------------------------------------------------------------
    @property
    def rate(self):
        """
        :return: State of the rate correction.
        """
        raw_value = self.command('-get ratecorrection')
        value = to_int(raw_value)
        return bool(value)

    @rate.setter
    def rate(self, value):
        """
        :param value: Activate/deactivate the rate correction.
        :return:
        """
        if type(value) != bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-ratecorrection %d' % int(value))

    # ------------------------------------------------------------------
    #   Readout
    # ------------------------------------------------------------------
    @property
    def readout(self):
        """
        :return: Numpy array with the count of each channels.
        """
        raw_value = self.command('-readout')
        values = to_int_list(raw_value)
        if values[0] == -1:
            raise MythenError(ERR_MYTHEN_READOUT)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    def readout_into(self, buff):
        return self.connection.write_read_exactly_into(b'-readout', buff)

    def ireadout(self, n=None, buff=None):
        # TODO: assert mythen version >= 4 (-readout 'n' only appears in v4)
        # TODO: should calculate nb channels based on nb active modules
        frame_channels = self.nchannels
        frame_bytes = frame_channels * 4
        if buff is None:
            if n is None:
                n = 1
            buff = np.empty((n, frame_channels), '<i4')
        else:
            buff_nb_frames = buff.nbytes // frame_bytes
            if n is None:
                n = buff_nb_frames
            else:
                assert n == buff_nb_frames
        flat = buff[:]
        flat.shape = flat.size
        self.connection.write('-readout {}'.format(n).encode())
        for i in range(n):
            offset = i*frame_channels
            view = flat[offset:offset + frame_channels]
            self.connection.read_exactly_into(view)
            yield i, view, buff

    # ------------------------------------------------------------------
    #   Readout Bits
    # ------------------------------------------------------------------
    @property
    def readoutbits(self):
        """
        :return: number of bits
        """
        raw_value = self.command('-get nbits')
        value = to_int(raw_value)
        return value

    @readoutbits.setter
    def readoutbits(self, value):
        """
        :param value: Bits of the readout: 4, 8, 16, 24
        :return:
        """
        if value not in COUNTER_BITS:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-nbits %d' % value)

    # ------------------------------------------------------------------
    #   Tau
    # ------------------------------------------------------------------
    @property
    def tau(self):
        """
        :return: Value of the current Tau
        """
        raw_value = self.command('-get tau')
        value = to_float(raw_value)
        value *= 100e-9
        return value

    @tau.setter
    def tau(self, value):
        """
        :param value: Value of Tau in seconds.
        :return:
        """
        if value < 0 and value != -1:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        if value != -1:
            value /= 100e-9
        self.command('-tau %f' % value)

    # ------------------------------------------------------------------
    #   Threshold
    # ------------------------------------------------------------------
    @property
    def threshold(self):
        """
        :return: Threshold value in keV.
        """
        raw_value = self.command('-get kthresh')
        value = to_float(raw_value)
        return value

    @threshold.setter
    def threshold(self, value):
        """
        :param value: Value of the energy threshold in keV
        :return:
        """
        if value < 0:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-kthresh %f' % value)

    # ------------------------------------------------------------------
    #   Version
    # ------------------------------------------------------------------
    @property
    def version(self):
        """
        :return: String with the firmware version.
        """
        value = self.command('-get version')
        if len(value) != 7:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return value[:-1].decode()

    # ------------------------------------------------------------------
    #   Triggers
    # ------------------------------------------------------------------

    @property
    def triggermode(self):
        return self._trigger

    @triggermode.setter
    def triggermode(self, value):
        if type(value) is not bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-trigen %d' % int(value))
        self._trigger = value

    @property
    def continuoustrigger(self):
        return self._trigger_cont

    @continuoustrigger.setter
    def continuoustrigger(self, value):
        if type(value) is not bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-conttrigen %d' % int(value))
        self._trigger_cont = value

    @property
    def gatemode(self):
        return self._gatemode

    @gatemode.setter
    def gatemode(self, value):
        if type(value) is not bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-gateen %d' % int(value))
        self._gatemode = value

    @property
    def outputhigh(self):
        return self._outputhigh

    @outputhigh.setter
    def outputhigh(self, value):
        if type(value) is not bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-outpol %d' % int(value))
        self._outputhigh = value

    @property
    def inputhigh(self):
        return self._inputhigh

    @inputhigh.setter
    def inputhigh(self, value):
        if type(value) is not bool:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-inpol %d' % int(value))
        self._inputhigh = value

    def set_active_modules(self, modules):
        self.command('-nmodules %d' % modules)

    def set_delay_trigger(self, time):
        ntimes = int(time / 100e-9)
        self.command('-delbef %d' % ntimes)

    def set_delay_frame(self, time):
        ntimes = int(time / 100e-9)
        self.command('-delafter %d' % ntimes)

    def set_num_gates(self, gates):
        self.command('-gates %d' % gates)

