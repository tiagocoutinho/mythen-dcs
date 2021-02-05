import socket
import struct
import logging
import functools
import threading
import contextlib
import urllib.parse

import numpy as np

COUNTER_BITS = [4, 8, 16, 24]

SETTINGS_MODES = ['StdCu', 'StdMo', 'HgCr', 'HgCu', 'FastCu', 'FastMo']
SETTINGS = ['Cu', 'Mo', 'Cr', 'Ag']
MATERIALS = {0: 'Si'}

TCP_PORT = 1031
UDP_PORT = 1030
TCP = socket.SOCK_STREAM
UDP = socket.SOCK_DGRAM
DEFAULT_TIMEOUT = object()

ERR_MYTHEN_COMM_LENGTH = -40
ERR_MYTHEN_COMM_TIMEOUT = -41
ERR_MYTHEN_READOUT = -42
ERR_MYTHEN_SETTINGS = -43
ERR_MYTHEN_BAD_PARAMETER = -44
ERR_MYHEN_CMD_REMOVED = -45
ERR_MYTHEN_COMM_ERROR = -46

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
    ERR_MYTHEN_BAD_PARAMETER: 'Bad parameter.',
    ERR_MYHEN_CMD_REMOVED: 'Mythen command not supported anymore',
    ERR_MYTHEN_COMM_ERROR: 'Mythen communication error'
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
        with self.lock:
            just_connected = False
            if self.socket is None:
                self.connect()
                just_connected =True
            if self.kind == UDP or just_connected:
                try:
                    return f(self, *args, **kwargs)
                except (socket.timeout, OSError):
                    self.disconnect()
                    raise
            try:
                result = f(self, *args, **kwargs)
                if isinstance(result, bytes) and not result:
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
    if timeout is DEFAULT_TIMEOUT:
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

    def __init__(self, host, port, timeout=DEFAULT_TIMEOUT, kind=TCP, log=None):
        self.host = host
        self.port  = port
        self.timeout = timeout
        self.kind = kind
        self.socket = None
        self.fobj = None
        self.lock = threading.Lock()
        if log is None:
            log = logging.getLogger('mythen.[{}:{} at {:x}]'.format(host, port, id(self)))
        self.log = log

    def __del__(self):
        self.disconnect()

    def __repr__(self):
        conn = "connected" if self.socket else "pending"
        kind = 'UDP' if self.kind == UDP else 'TCP'
        return "<{} {} {}>".format(kind, conn, (self.host, self.port))

    @classmethod
    def from_url(cls, url, timeout=DEFAULT_TIMEOUT):
        """Default scheme is TCP"""
        if "://" not in url:
            url = "tcp://" + url
        url = urllib.parse.urlparse(url)
        kind = UDP if url.scheme == "udp" else TCP
        return cls(url.hostname, url.port, timeout=timeout, kind=kind)

    def connect(self):
        self.disconnect()
        sock = socket.socket(socket.AF_INET, type=self.kind)
        if self.timeout != DEFAULT_TIMEOUT:
            sock.settimeout(self.timeout)
        self.log.info("-> connecting")
        sock.connect((self.host, self.port))
        self.fobj = sock.makefile("rwb", buffering=0)
        self.log.info("<- connected!")
        self.socket = sock

    def disconnect(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
            self.fobj = None

    def fileno(self):
        return None if self.socket is None else self.socket.fileno()

    def _read_exactly_into(self, buff):
        try:
            size = buff.nbytes
            buff = buff.view(dtype=np.byte)
        except AttributeError:
            size = len(buff)
        offset = 0
        while offset < size:
            n = self.socket.recv_into(buff[offset:], size - offset)
            if not n:
                raise MythenError(ERR_MYTHEN_COMM_ERROR)
            offset += n
        return buff

    @ensure_connection
    def write(self, data):
        self.fobj.write(data)

    @ensure_connection
    def read(self, size, timeout=DEFAULT_TIMEOUT):
        self.log.debug("-> read(%s)", size)
        with guard_timeout(self, timeout):
            reply = self.fobj.read(size)
        self.log.debug("<- read %d bytes", len(reply))
        return reply

    @ensure_connection
    def read_exactly_into(self, buff, timeout=DEFAULT_TIMEOUT):
        self.log.debug("-> read_exactly_into(%s)", buff.nbytes)
        with guard_timeout(self, timeout):
            reply = self._read_exactly_into(buff)
        self.log.debug("<- read_exactly_into %d bytes", reply.nbytes)
        return reply

    @ensure_connection
    def write_read(self, data, size, timeout=DEFAULT_TIMEOUT):
        self.log.debug("-> write_read(%r, %d)", data, size)
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            reply = self.fobj.read(size)
        self.log.debug("<- write_read(%r)", reply)
        return reply

    @ensure_connection
    def write_read_exactly_into(self, data, buff, timeout=DEFAULT_TIMEOUT):
        self.log.debug("-> write_read_exactly_into(%r)", data)
        with guard_timeout(self, timeout):
            self.fobj.write(data)
            reply = self._read_exactly_into(buff)
        self.log.debug("<- write_read_exactly_into %d bytes", len(reply))
        return reply


def to_int(d):
    return struct.unpack_from("<i", d)[0]


def to_long_long(d):
    return struct.unpack_from("<q", d)[0]


def to_float(d):
    return struct.unpack_from("<f", d)[0]


def to_int_list(d):
    return np.frombuffer(d, dtype="<i4")


def to_float_list(d):
    return np.frombuffer(d, dtype="<f4")


def command(connection, cmd, size=8192, timeout=DEFAULT_TIMEOUT):
    """
    Send command to Mythen. It verifies if there are errors.
    :param cmd: Command
    :return: Answer
    """
    cmd = cmd.encode() if isinstance(cmd, str) else cmd
    try:
        raw_value = connection.write_read(cmd, size, timeout=timeout)
    except socket.timeout:
        raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    # sizeof(int)
    if len(raw_value) == 4:
        value = to_int(raw_value)
        if value < 0:
            raise MythenError(value)
    return raw_value


def version(connection, timeout=DEFAULT_TIMEOUT):
    value = command(connection, '-get version', timeout=timeout)
    if len(value) != 7:
        raise MythenError(ERR_MYTHEN_COMM_LENGTH)
    return [int(part) for part in value[1:-1].split(b'.')]


class Mythen:
    """
    Class to control the Mythen. Exported API:

    """
    MAX_BUFF_SIZE_MODULE = 10000
    MAX_CHANNELS = 1280
    MASK_RUNNING = 1  # Bit 0
    MASK_WAIT_TRIGGER = 1 << 3  # Bit 3
    MASK_FIFO_EMPTY = 1 << 16  # Bit 16

    def __init__(self, connection, nmod=1, log=None):
        """
        :param connection
        :param nmod: Number of modules
        """
        if log is None:
            name = type(self).__name__
            host, port = connection.host, connection.port
            log = logging.getLogger('mythen.{}({}:{})'.format(name, host, port))
        self.log = log
        self.connection = connection
        self.buff = nmod * self.MAX_BUFF_SIZE_MODULE
        self.nchannels = nmod * self.MAX_CHANNELS
        self.nmods = nmod
        self.frames = 1
        self.triggermode = False
        self.gatemode = False
        self.inputhigh = True
        self.outputhigh = True
        self.continuoustrigger = False

    @classmethod
    def from_url(cls, url, nmod=1):
        if "://" not in url:
            tmp_url = urllib.parse.urlparse("void://" + url)
            scheme = "udp" if tmp_url.port == UDP_PORT else "tcp"
            url = "{}://{}".format(scheme, url)
        url = urllib.parse.urlparse(url)
        scheme, port = url.scheme, url.port
        if port is None:
            port = UDP_PORT if scheme == "udp" else TCP_PORT
        url = "{}://{}:{}".format(scheme, url.hostname, port)
        return cls(Connection.from_url(url), nmod=nmod)

    # ------------------------------------------------------------------
    #   Commands
    # ------------------------------------------------------------------
    def command(self, cmd, timeout=DEFAULT_TIMEOUT):
        """
        Method to send command to Mythen. It verifies if there are errors.
        :param cmd: Command
        :return: Answer
        """
        return command(self.connection, cmd, size=self.buff, timeout=timeout)

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
        timeout = 2.5 + 0.75 * self.nmods
        self.command('-reset', timeout=timeout)
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
        values = np.empty(self.nchannels, dtype='<i4')
        return self.connection.write_read_exactly_into(b'-get flatfield', values)

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

    def set_active_modules(self, modules):
        if self.get_active_modules() == modules:
            self.log.info('nb. active modules already at %d. Skipping!', modules)
            return
        self.command('-nmodules %d' % modules)

    def set_module(self, value):
        if value not in list(range(self.nmods)):
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
        # the buffer we get is read-only (numpy view of raw_value).
        # We need a copy to be able to process it (ns -> seconds)
        value = to_float_list(raw_value).copy()
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
        value = to_float_list(raw_value)
        return value

    @threshold.setter
    def threshold(self, value):
        """
        :param value: Value of the energy threshold in keV
        :return:
        """
        if value < 0:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        # this command takes ~0.5s per module
        timeout = 0.75 * self.nmods
        self.command('-kthresh %f' % value, timeout=timeout)

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

    def get_delay_trigger(self):
        return to_int(self.command('-get delbef')) * 100e-9

    def set_delay_trigger(self, time):
        ntimes = int(time / 100e-9)
        self.command('-delbef %d' % ntimes)

    delay_trigger = property(get_delay_trigger, set_delay_trigger)

    def get_delay_frame(self):
        return to_int(self.command('-get delafter')) * 100e-9

    def set_delay_frame(self, time):
        ntimes = int(time / 100e-9)
        self.command('-delafter %d' % ntimes)

    delay_frame = property(get_delay_frame, set_delay_frame)

    def get_num_gates(self):
        return to_int(self.command('-get gates'))

    def set_num_gates(self, gates):
        self.command('-gates %d' % gates)

    num_gates = property(get_num_gates, set_num_gates)


class Mythen4(Mythen):

    def __init__(self, connection, nmod=None, log=None):
        if log is None:
            name = type(self).__name__
            host, port = connection.host, connection.port
            log = logging.getLogger('mythen.{}({}:{})'.format(name, host, port))
        self.log = log
        self._num_module_channels = None
        self.connection = connection
        self.buff = (nmod or 4) * self.MAX_BUFF_SIZE_MODULE
        if nmod is None:
            nmod = self.active_modules
        self.active_modules = nmod
        self.frames = 1
        self.triggermode = False
        self.gatemode = False
        self.continuoustrigger = False

    def _update(self):
        self._num_module_channels = None
        active_modules = self.active_modules
        channels = self.num_module_channels
        nchannels = channels.sum()
        self.nmods = active_modules
        self.nchannels = nchannels
        self.buff = 4 * nchannels # 4 == sizeof(int32)

    def get_active_modules(self):
        return super().get_active_modules()

    def set_active_modules(self, value):
        super().set_active_modules(value)
        self._update()

    active_modules = property(get_active_modules, set_active_modules)

    @property
    def num_module_channels(self):
        """Returns the number of channels for each module."""
        if self._num_module_channels is None:
            raw_value = self.command('-get modchannels')
            self._num_module_channels = to_int_list(raw_value)
        return self._num_module_channels

    @property
    def num_channels(self):
        """Returns the total number of channels"""
        return self.num_module_channels.sum()

    @property
    def max_num_modules(self):
        return to_int(self.command("-get nmaxmodules"))

    @property
    def max_frame_rate(self):
        return to_float(self.command("-get frameratemax"))

    @property
    def assembly_date(self):
        return self.command("-get assemblydate").strip(b'\x00').strip().decode()

    @property
    def firmware_version(self):
        return self.command("-get fwversion").strip(b'\x00').decode()

    @property
    def system_serial_number(self):
        return to_int(self.command("-get systemnum"))

    @property
    def temperature(self):
        return to_float(self.command("-get dcstemperature"))

    def get_module(self):
        return to_int(self.command("-get module"))

    def set_module(self, value):
        return super().set_module(value)

    module = property(get_module, set_module)

    @property
    def module_high_voltages(self):
        return to_int_list(self.command("-get hv"))

    @property
    def module_temperatures(self):
        return to_float_list(self.command("-get temperature"))

    @property
    def module_humidities(self):
        return to_float_list(self.command("-get humidity"))

    @property
    def module_serial_numbers(self):
        return to_int_list(self.command("-get modnum"))

    @property
    def module_firmware_versions(self):
        raw_data = self.command("-get modfwversion").strip(b'\x00').decode()
        return [raw_data[i:i+8] for i in range(0, len(raw_data), 8)]

    @property
    def module_sensor_materials(self):
        materials = to_int_list(self.command("-get sensormaterial"))
        return [MATERIALS[material] for material in materials]

    @property
    def module_sensor_thicknesses(self):
        """sensors thickness (μm)"""
        return to_int_list(self.command("-get sensorthickness"))

    @property
    def module_sensor_widths(self):
        """sensors width (μm)"""
        return to_int_list(self.command("-get sensorwidth"))

    @property
    def energy(self):
        return to_float_list(self.command("-get energy"))

    @energy.setter
    def energy(self, value):
        return self.command("-energy {}".format(value))

    @property
    def cutoff(self):
        return to_int(self.command('-get cutoff'))

    @cutoff.setter
    def cutoff(self, value):
        self.command('-cutoff %d' % value)

    @property
    def outputhigh(self):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @outputhigh.setter
    def outputhigh(self, value):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @property
    def inputhigh(self):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @inputhigh.setter
    def inputhigh(self, value):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @property
    def settingsmode(self):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @settingsmode.setter
    def settingsmode(self, value):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    def autosettings(self, value):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    @property
    def settings(self):
        raise MythenError(ERR_MYHEN_CMD_REMOVED)

    def activate_flatfield(self, slot):
        """Activates specific customer pre-stored flatfield"""
        assert slot in {0, 1, 2, 3}
        self.command('-loadflatfield {}'.format(slot))

    def upload_flatfield(self, slot, flatfield):
        """flatfield should be a numpy array dtype '<u4'"""
        assert slot in {0, 1, 2, 3}
        cmd = "-flatfield {} ".format(slot).encode()
        self.command(cmd + flatfield.tobytes())

    @settings.setter
    def settings(self, value):
        """
        :param value: String with the setting mode: Cu, Mo, Cr, Ag
        """
        if value not in SETTINGS:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-settings %s' % value)

    def ireadout(self, n=None, buff=None):
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
                assert n <= buff_nb_frames
        flat = buff[:]
        flat.shape = flat.size
        cmd = '-readout' if n == 1 else '-readout {}'.format(n)
        self.connection.write(cmd.encode())
        for i in range(n):
            offset = i*frame_channels
            view = flat[offset:offset + frame_channels]
            self.connection.read_exactly_into(view)
            yield i, view, buff

    def gen_readout(self, n, buffers):
        cmd = '-readout' if n == 1 else '-readout {}'.format(n)
        self.connection.write(cmd.encode())
        for i in range(n):
            buff = next(buffers)
            self.connection.read_exactly_into(buff)
            yield buff


def mythen_for_url(url, nmod=None, timeout=DEFAULT_TIMEOUT):
    if "://" not in url:
        tmp_url = urllib.parse.urlparse("void://" + url)
        scheme = "udp" if tmp_url.port == UDP_PORT else "tcp"
        url = "{}://{}".format(scheme, url)
    url = urllib.parse.urlparse(url)
    scheme, port = url.scheme, url.port
    if port is None:
        port = UDP_PORT if scheme == "udp" else TCP_PORT
    url = "{}://{}:{}".format(scheme, url.hostname, port)
    conn = Connection.from_url(url, timeout=timeout)
    vers = version(conn)
    if vers[0] >= 4:
        klass = Mythen4
    else:
        if nmod is None:
            nmod = 1
        klass = Mythen
    return klass(conn, nmod=nmod)


def acquire(mythen, exposure_time=1, nb_frames=1):
    mythen.inttime = exposure_time
    mythen.frames = nb_frames
    nchannels = mythen.nchannels
    def gen_buffers():
        while True:
            yield np.empty(nchannels, '<i4')
    mythen.start()
    for frame in mythen.gen_readout(nb_frames, gen_buffers()):
        print(frame)
