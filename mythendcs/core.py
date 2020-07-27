import socket
import struct
import functools
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


class MythenError(Exception):
    def __init__(self, value, *args):
        self.errcode = value
        self.args = args

    def __str__(self):
        return self._get_error_msg(self.errcode)

    def _get_error_msg(self, value):
        if value == -1:
            msg = 'Error %d: Unknown command' % value
        elif value == -2:
            msg = 'Error %d: Invalid argument' % value
        elif value == -3:
            msg = 'Error %d: Unknown settings' % value
        elif value == -4:
            msg = 'Error %d: Out of memory' % value
        elif value == -5:
            msg = 'Error %d: Module calibration files not found' % value
        elif value == -6:
            msg = 'Error %d: Readout failed' % value
        elif value == -10:
            msg = 'Error %d: Flat field not found' % value
        elif value == -11:
            msg = 'Error %d: Bad channel file not found' % value
        elif value == -12:
            msg = 'Error %d: Energy calibration not found' % value
        elif value == -13:
            msg = 'Error %d: Noise file not found' % value
        elif value == -14:
            msg = 'Error %d: Trim bit file not found' % value
        elif value == -15:
            msg = 'Error %d: Invalid format of the flat field file' % value
        elif value == -16:
            msg = 'Error %d: Invalid format of the bad channel file' % value
        elif value == -17:
            msg = ('Error %d: Invalid format of the energy calibration file'
                   % value)
        elif value == -18:
            msg = 'Error %d: Invalid format of the noise file' % value
        elif value == -19:
            msg = 'Error %d: Invalid format of the trim bit file' % value
        elif value == -30:
            msg = 'Error %d: Could not create log file' % value
        elif value == -31:
            msg = 'Error %d: Could not close log file' % value
        elif value == -32:
            msg = 'Error %d: Could not read log file' % value
        elif value == ERR_MYTHEN_COMM_LENGTH:
            msg = ('Error %d: Error with the communication, the response size '
                   'is greater than the default.' % value)
        elif value == ERR_MYTHEN_COMM_TIMEOUT:
            msg = ('Error %d: Error timed out, the device did not respond. '
                   % value)
        elif value == ERR_MYTHEN_READOUT:
            msg = ('Error %d: Error with the readout command. '
                   % value)
        elif value == ERR_MYTHEN_SETTINGS:
            msg = ('Error %d: Return and unknown settings code (%d).'
                   % (value, self.args[0]))
        elif value == ERR_MYTHEN_BAD_PARAMETER:
            msg = 'Error %d: Bad parameter.' % value
        else:
            msg = 'Unknown error code (%d)' % value

        return msg


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
def guard_timeout(channel, timeout):
    if timeout == -1:
        yield
    else:
        prev_timeout = channel.socket.gettimeout()
        channel.socket.settimeout(timeout)
        try:
            yield
        finally:
            if channel.socket:
                channel.socket.settimeout(prev_timeout)


class Channel:
    """Communication channel"""

    def __init__(self, host, port, timeout=None, kind=None):
        self.host = host
        self.port  = port
        self.timeout = timeout
        self._kind = kind
        self.socket = None
        self.fobj = None

    def __del__(self):
        self.disconnect()

    def __repr__(self):
        conn = "connected" if self.socket else "pending"
        kind = 'UDP' if self.kind == UDP else 'TCP'
        return "<{} {} {}>".format(kind, conn, (self.host, self.port))

    @property
    def kind(self):
        if self._kind is None:
            return (UDP if self.port == UDP_PORT else TCP)
        return self._kind

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
            offset = 0
            while offset < size:
                print(offset, size)
                offset += self.socket.recv_into(buff[offset:])
            return buff

    @ensure_connection
    def write(self, data):
        self.fobj.write(data)

    @ensure_connection
    def read(self, size, timeout=-1):
        with guard_timeout(self, timeout):
            return self.fobj.read(size)

    @ensure_connection
    def read_exactly_into(self, buff, timeout=-1):
        with guard_timeout(self, timeout):
            return self._read_exactly_into(buff)

    @ensure_connection
    def write_read(self, data, size, timeout=-1):
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            return self.fobj.read(size)

    @ensure_connection
    def write_read_exactly_into(self, data, buff, timeout=-1):
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            self._read_exactly_into(buff)

to_int = struct.Struct("<i").unpack
to_long_long = struct.Struct("<q").unpack
to_float = struct.Struct("<f").unpack


def _to_int_list(self, raw_value):
    fmt = "<%di" % (len(raw_value) // 4)
    return np.array(struct.unpack(fmt, raw_value))


class Mythen:
    """
    Class to control the Mythen. Exported API:

    """
    MAX_BUFF_SIZE_MODULE = 10000
    MAX_CHANNELS = 1280
    MASK_RUNNING = 1  # Bit 0
    MASK_WAIT_TRIGGER = 1 << 3  # Bit 3
    MASK_FIFO_EMPTY = 1 << 16  # Bit 16

    def __init__(self, channel, nmod=1):
        """
        :param channel
        :param port: UDP_PORT or TCP_PORT
        :param timeout:
        :param nmod: Number of modules
        :return:          self.conn.write(cmd.encode() if isinstance(cmd, str) else cmd)
      self.conn.write(cmd.encode() if isinstance(cmd, str) else cmd)

        """
        self.channel = channel
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
            self.channel.write(cmd.encode() if isinstance(cmd, str) else cmd)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    def _receive_msg(self):
        try:
            return self.channel.read(self.buff)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    def _to_int(self, raw_value):
        return struct.unpack('i', raw_value)

    def _to_int_list(self, raw_value):
        fmt = "<%di" % (len(raw_value) // 4)
        return np.array(struct.unpack(fmt, raw_value))

    def _to_long_long(self, raw_value):
        return struct.unpack('<q', raw_value)

    def _to_float(self, raw_value):
        return struct.unpack('f', raw_value)

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
            raw_value = self.channel.write_read(cmd, self.buff, timeout=timeout)
        except socket.timeout:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

        # sizeof(int)
        if len(raw_value) == 4:
            value = self._to_int(raw_value)[0]
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
        values = self._to_int_list(raw_value)
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
        value = self._to_int(raw_value)[0]
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
        values = self._to_int_list(raw_value)
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_long_long(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        value = self._to_int(raw_value)[0]
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
        values = self._to_int_list(raw_value)
        if values[0] == -1:
            raise MythenError(ERR_MYTHEN_READOUT)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    # ------------------------------------------------------------------
    #   Readout Bits
    # ------------------------------------------------------------------
    @property
    def readoutbits(self):
        """
        :return: number of bits
        """
        raw_value = self.command('-get nbits')
        value = self._to_int(raw_value)[0]
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
        value = self._to_float(raw_value)[0]
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
        value = self._to_float(raw_value)[0]
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
        return value

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

