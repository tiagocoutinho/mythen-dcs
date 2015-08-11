import socket
import struct
import numpy as np

COUNTER_BITS = [4, 8, 16, 24]

SETTINGS_MODES = ['StdCu', 'StdMo', 'HgCr', 'HgCu', 'FastCu', 'FastMo']

TCP_PORT = 1031
UDP_PORT = 1030

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
                   %(value, self.args[0]))
        elif value == ERR_MYTHEN_BAD_PARAMETER:
            msg = 'Error %d: Bad parameter.' % value
        else:
            msg = 'Unknown error code (%d)' % value

        return msg

class Mythen(object):
    """
    Class to control the Mythen. Exported API:

    """
    MAX_BUFF_SIZE_MODULE = 10000
    MAX_CHANNELS = 1280
    MASK_RUNNING = 1  # Bit 0
    MASK_WAIT_TRIGGER = 8  # Bit 3

    def __init__(self, ip, port, timeout=3, nmod=1):
        """
        :param ip: Mythen IP
        :param port: UDP_PORT or TCP_PORT
        :param timeout:
        :param nmod: Number of modules
        :return:
        """
        self.ip = ip
        self.port = port
        self.socket_conf = (ip, port)
        self.mythen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mythen_socket.settimeout(timeout)
        self.buff = nmod * self.MAX_BUFF_SIZE_MODULE
        self.nchannels = nmod * self.MAX_CHANNELS
        self.frames = 1

    def _send_msg(self, cmd):
        """
        :param cmd: Command
        :return:
        """
        try:
            self.mythen_socket.sendto(cmd, self.socket_conf)
        except socket.timeout, e:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    def _receive_msg(self):
        """
        :return: String with the answer.
        """
        try:
            result, socket_rsv = self.mythen_socket.recvfrom(self.buff)
        except socket.timeout, e:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

        return result

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
    def command(self, cmd):
        """
        Method to send command to Mythen. It verifies if there are errors.
        :param cmd: Command
        :return: Answer
        """
        self._send_msg(cmd)
        raw_value = self._receive_msg()
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
        self.command('-reset')

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
        :param frames: Number of frames per acquisition.
        :return:
        """
        self.command('-frames %d' %value)
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
        # Exposure value in uints of 100ns.
        ntimes = long(value / 100e-9)
        self.command('-time %d' % ntimes)

    # ------------------------------------------------------------------
    #   M
    # ------------------------------------------------------------------

    def get_active_modules(self):
        raw_value = self.command('-get nmodules')
        value = self._to_int(raw_value)[0]
        return value

    def set_module(self, value):
        if value not in range(self.nmod):
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
        raw = self.command('-get settingsmode')
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
        elif value & self.MASK_WAIT_TRIGGER:
            state = 'WAIT_TRIGGER'
        else:
            state = 'ON'
        return state

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








    # TODO organize the trigger configuration.





    def get_trigger(self):
        return self.trigger

    def get_cont_trigger(self):
        return self.trigger_cont

    def set_active_modules(self, modules):
        self.command('-nmodules %d' % modules)

    def set_output_high(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('outpol %d' %i)

    def set_input_high(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('outpol %d' %i)



    def set_cont_trigger(self, value):
        i = int (value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-conttrigen %d' % i)
        self.trigger_cont = True

    def set_delay_trigger(self, time):
        ntimes = long(time / 100e-9)
        self.command('-delbef %d' % ntimes)

    def set_delay_frame(self, time):
        ntimes = long(time / 100e-9)
        self.command('-delafter %d' % ntimes)



    def set_gate(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-gateen %d' % i)

    def set_num_gates(self, gates):
        self.command('-gates %d' % gates)


    def set_trigger(self, value):
        i = int(value)
        if i not in[0, 1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-trigen %d' % i)
        self.trigger = True


    def set_input_high(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-inpol %d' % i)






    def __del__(self):
        self.mythen_socket.close()



