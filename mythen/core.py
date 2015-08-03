__author__ = 'rhoms'

import socket
import struct


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
            msg = 'Error %d: Flatfield not found' % value
        elif value == -11:
            msg = 'Error %d: Bad channel file not found' % value
        elif value == -12:
            msg = 'Error %d: Energy calibration not found' % value
        elif value == -13:
            msg = 'Error %d: Noise file not found' % value
        elif value == -14:
            msg = 'Error %d: Trimbit file not found' % value
        elif value == -15:
            msg = 'Error %d: Invalid format of the flatfield file' % value
        elif value == -16:
            msg = 'Error %d: Invalid format of the bad channel file' % value
        elif value == -17:
            msg = ('Error %d: Invalid format of the energy calibration file'
                   % value)
        elif value == -18:
            msg = 'Error %d: Invalid format of the noise file' % value
        elif value == -19:
            msg = 'Error %d: Invalid format of the trimbit file' % value
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
    MAX_BUFF_SIZE_MODULE = 10000
    MAX_CHANNELS = 1280
    MASK_RUNNING = 1 #Bit 0
    MASK_WAIT_TRIGGER = 8 #Bit 3

    def __init__(self, ip, port, timeout=3, nmod=1):
        self.ip = ip
        self.port = port
        self.socket_conf = (ip,port)
        self.mythen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mythen_socket.settimeout(timeout)
        self.nmod = nmod
        self.buff = nmod * self.MAX_BUFF_SIZE_MODULE
        self.nchannels = nmod * self.MAX_CHANNELS
        self.trigger = False
        self.trigger_cont = False
        self.frames = 1

    def _send_msg(self,cmd):
        try:
            self.mythen_socket.sendto(cmd,self.socket_conf)
        except socket.timeout, e:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

    def _receive_msg(self):
        try:
            result, socket_rsv = self.mythen_socket.recvfrom(self.buff)
        except socket.timeout, e:
            raise MythenError(ERR_MYTHEN_COMM_TIMEOUT)

        return result

    def _to_int(self,raw_value):
        return struct.unpack('i',raw_value)

    def _to_int_list(self,raw_value):
        fmt = "<%di" % (len(raw_value) // 4)
        return struct.unpack(fmt,raw_value)

    def _to_long_long(self, raw_value):
        return struct.unpack('<q',raw_value)

    def _to_float(self,raw_value):
        return struct.unpack('f',raw_value)

    def command(self, cmd):
        self._send_msg(cmd)
        raw_value = self._receive_msg()
        # sizeof(int)
        if len(raw_value) == 4:
            value = self._to_int(raw_value)[0]
            if value < 0:
                raise MythenError(value)
        return raw_value

    def get_version(self):
        value = self.command('-get version')
        if len(value) != 7:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return value

    def get_tau(self):
        raw_value = self.command('-get tau')
        value = self._to_float(raw_value)[0]
        value *= 100e-9
        return value

    def get_settings_mode(self):
        value = self.command('-get settingsmode')
        return value

    def get_readout(self):
        raw_value = self.command('-readout')
        err = all([i == -1 for i in raw_value])
        if err:
            raise MythenError(ERR_MYTHEN_READOUT)
        values = self._to_int_list(raw_value)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    def get_status(self):
        raw_value = self.command('-get status')
        value = self._to_int(raw_value)[0]
        if value & self.MASK_RUNNING:
            state = 'RUNNING'
        elif value & self.MASK_WAIT_TRIGGER:
            state = 'WAIT_TRIGGER'
        else:
            state = 'ON'
        return state

    def get_bad_channel_interpolation(self):
        raw_value = self.command('-get badchannelinterpolation')
        value = self._to_int(raw_value)[0]
        return bool(value)

    def get_bad_channels(self):
        raw_value = self.command('-get badchannels')
        values = self._to_int_list(raw_value)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    def get_flat_field(self):
        raw_value = self.command('-get flatfield')
        values = self._to_int_list(raw_value)
        if len(values) != self.nchannels:
            raise MythenError(ERR_MYTHEN_COMM_LENGTH)
        return values

    def get_flat_field_correction(self):
        raw_value = self.command('-get flatfieldcorrection')
        value = self._to_int(raw_value)[0]
        return bool(value)

    def get_threshold(self):
        raw_value = self.command('-get kthresh')
        value = self._to_float(raw_value)[0]
        return value

    def get_bits_readout(self):
        raw_value = self.command('-get nbits')
        value = self._to_int(raw_value)[0]
        return value

    def get_active_modules(self):
        raw_value = self.command('-get nmodules')
        value = self._to_int(raw_value)[0]
        return value

    def get_rate_correction(self):
        raw_value = self.command('-get ratecorrection')
        value = self._to_int(raw_value)[0]
        return bool(value)

    def get_settings(self):
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

    def get_time(self):
        raw_value = self.command('-get time')
        value = self._to_long_long(raw_value)[0]
        value *= 100e-9 #Time in seconds
        return value

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

    def set_rate_correction(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('outpol %d' %i)

    def set_bad_channels_interpolation(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-badchannelinterpolation %d' % i)

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

    def set_flat_field_correction(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-flatfieldcorrection %d' % d)

    def set_frames(self, frames):
        self.command('-frames %d' %frames)

    def set_gate(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-gateen %d' % i)

    def set_num_gates(self, gates):
        self.command('-gates %d' % gates)

    def set_time(self, time):
        # Time in seconds
        # Exposure time in uints of 100ns.
        ntimes = long(time / 100e-9)
        self.command('-time %d' % ntimes)

    def set_trigger(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-trigen %d' % i)
        self.trigger = True

    def set_tau(self, value):
        if value < 0 and value != -1:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        if value != -1:
            value /= 100e-9
        self.command('-tau %f' % value)

    def set_input_high(self, value):
        i = int(value)
        if i not in[0,1]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-inpol %d' % i)

    def set_threshold(self, value):
        if value < 0:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-kthresh %f' % value)

    def set_bits_readout(self, value):
        if value not in [4, 8, 16, 24]:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-nbits %d' % value)

    def set_module(self, value):
        if value not in range(self.nmod):
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-module %d' % value)

    def set_settings(self, value):
        if value not in ['StdCu', 'StdMo', 'HgCr', 'HgCu', 'FastCu', 'FastMo']:
            raise MythenError(ERR_MYTHEN_BAD_PARAMETER)
        self.command('-settings %s' % value)

    def start_acquisition(self):
        self.command('-start')

    def stop_acquisition(self):
        self.command('-stop')

    def reset(self):
        self.command('reset')

    def __del__(self):
        self.mythen_socket.close()



