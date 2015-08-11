#   '$Name:  $pp`';
#   '$Header:  $';
# =============================================================================
#
# file :       device.py
#
# description : Device server to control the Mythen Detector from Dectris. It
#  base on the Socket version 2.0.2
#
# project :     TANGO Device Server
#
# $Author:  Roberto Homs
#
# $Revision:  $
#
# $Log:  $
#
# copyleft :    Alba Synchrotron Radiation Facility
#               Cerdanyola del Valles
#               Spain
#
#
#         (c) - Controls group - ALBA
# =============================================================================

import PyTango
import time
from mythendcs import Mythen, UDP_PORT, TCP_PORT, COUNTER_BITS, \
    SETTINGS_MODES, MythenError
import threading
import numpy as np

DEV_STATE_UNKNOWN = PyTango.DevState.UNKNOWN
DEV_STATE_FAULT = PyTango.DevState.FAULT
DEV_STATE_MOVING = PyTango.DevState.MOVING
DEV_STATE_ON = PyTango.DevState.ON
DEV_STATE_INIT = PyTango.DevState.INIT



# Decorator for managing the exception
def ExceptionHandler(func):
    def new_func(*args, **kwargs):
        try:
            obj = args[0]
            obj.debug_stream('Entering in %s (%s)' % (func.__name__,
                                                      repr(args)))
            func(*args, **kwargs)
            obj.debug_stream('Exiting %s' % func.__name__)
        except Exception, e:
            obj.warn_stream('Hardware warning in %s: %s' % (func.__name__, e))
            raise e
    return new_func

class MythenDCSClass(PyTango.DeviceClass):

    # Class Properties
    class_property_list = {
        }

    # Device Properties
    device_property_list = {
        'HostIP': [PyTango.DevString, 'Mythen IP', ''],
        'Port': [PyTango.DevString, 'TPC or UDP', 'UDP'],
        'NMod': [PyTango.DevLong, 'Number of modules connected', 1],
        'Timeout': [PyTango.DevLong, 'Serial port timeout', 3]
        }

    # Command definitions
    cmd_list = {'Reset': [[PyTango.DevVoid, 'None'],
                         [PyTango.DevVoid, 'None']],
                'Start': [[PyTango.DevVoid, 'None'],
                         [PyTango.DevVoid, 'None']],
                'Stop': [[PyTango.DevVoid, 'None'],
                         [PyTango.DevVoid, 'None']],
                'AutoSettings': [[PyTango.DevDouble, 'None'],
                                 [PyTango.DevVoid, 'None']],

                }

    # Attributes list
    attr_list = {
        'Version': [[PyTango.ArgType.DevString,
                     PyTango.AttrDataFormat.SCALAR,
                     PyTango.AttrWriteType.READ]],
        'ReadoutBits': [[PyTango.ArgType.DevShort,
                         PyTango.AttrDataFormat.SCALAR,
                         PyTango.AttrWriteType.READ_WRITE]],
        'RateCorrection': [[PyTango.ArgType.DevBoolean,
                            PyTango.AttrDataFormat.SCALAR,
                            PyTango.AttrWriteType.READ_WRITE]],
        'FlatFieldCorrection': [[PyTango.ArgType.DevBoolean,
                                 PyTango.AttrDataFormat.SCALAR,
                                 PyTango.AttrWriteType.READ_WRITE]],
        'BadChnInterp': [[PyTango.ArgType.DevBoolean,
                          PyTango.AttrDataFormat.SCALAR,
                          PyTango.AttrWriteType.READ_WRITE]],
        'Settings': [[PyTango.ArgType.DevString,
                      PyTango.AttrDataFormat.SCALAR,
                      PyTango.AttrWriteType.READ]],
        'SettingsMode': [[PyTango.ArgType.DevString,
                          PyTango.AttrDataFormat.SCALAR,
                          PyTango.AttrWriteType.READ_WRITE]],
        'Tau': [[PyTango.ArgType.DevDouble,
                 PyTango.AttrDataFormat.SCALAR,
                 PyTango.AttrWriteType.READ_WRITE]],
        'IntTime': [[PyTango.ArgType.DevDouble,
                  PyTango.AttrDataFormat.SCALAR,
                  PyTango.AttrWriteType.READ_WRITE],
                    {'min value': 0.05}],
        'Frames': [[PyTango.ArgType.DevULong64,
                    PyTango.AttrDataFormat.SCALAR,
                    PyTango.AttrWriteType.READ_WRITE]],
        'RawData': [[PyTango.ArgType.DevLong,
                        PyTango.AttrDataFormat.SPECTRUM,
                        PyTango.AttrWriteType.READ, 1280]],
        'LiveMode': [[PyTango.ArgType.DevBoolean,
                      PyTango.AttrDataFormat.SCALAR,
                      PyTango.AttrWriteType.READ_WRITE]],
        'ROIData':  [[PyTango.ArgType.DevULong64,
                      PyTango.AttrDataFormat.SCALAR,
                      PyTango.AttrWriteType.READ]],
        'ROI': [[PyTango.ArgType.DevLong,
                 PyTango.AttrDataFormat.SPECTRUM,
                 PyTango.AttrWriteType.READ_WRITE, 2]],
        'Threshold': [[PyTango.ArgType.DevDouble,
                       PyTango.AttrDataFormat.SCALAR,
                       PyTango.AttrWriteType.READ_WRITE],
                       {'min value': 0.05}],


    # TODO: Implement the other attributes.
    }

    def __init__(self, name):
        PyTango.DeviceClass.__init__(self, name)
        self.set_type("MythenDCSDevice")

class MythenDCSDevice(PyTango.Device_4Impl):
    # ------------------------------------------------------------------
    #   Device constructor
    # ------------------------------------------------------------------
    def __init__(self, cl, name):

        PyTango.Device_4Impl.__init__(self, cl, name)
        self.info_stream('In MythenDCSDevice.__init__')
        try:
            self.init_device()
        except Exception, e:
            self.set_state(DEV_STATE_FAULT)
            self.error_stream('Hardware error in __init__(): %s' % e)
            raise e
        self.state_machine()

    # ------------------------------------------------------------------
    #   Device destructor
    # ------------------------------------------------------------------
    def delete_device(self):
        self.mythen.__del__()
        self.info_stream('In %s::delete_device()' % self.get_name())

    # ------------------------------------------------------------------
    #   Device initialization
    # ------------------------------------------------------------------
    def init_device(self):
        self.info_stream('In %s::init_device()' % self.get_name())
        self.get_device_properties(self.get_device_class())
        port = UDP_PORT
        if self.Port == 'TCP':
            port = TCP_PORT
        self.mythen = Mythen(self.HostIP, port, self.Timeout, self.NMod)
        # Initialize attributes
        self.live_mode = False
        self.async = False
        self.raw_data = np.zeros(1280)
        self.roi_data = 0
        self.stop_flag = False
        self.roi = [0, 1280]

        # Define events on attributes
        self.set_change_event('RawData', True, False)
        self.set_change_event('ROIData', True, False)
        #self.set_change_event('LiveData', True, False)

    # ------------------------------------------------------------------
    #   State machine implementation
    # ------------------------------------------------------------------
    @ExceptionHandler
    def state_machine(self):
        if self.async:
            return
        status = self.mythen.status
        if status in ['RUNNING', 'WAIT_TRIGGER']:
            self.set_state(DEV_STATE_MOVING)
        elif status == 'ON':
            self.set_state(DEV_STATE_ON)
        else:
            self.set_state(DEV_STATE_UNKNOWN)
        self.set_status(status)

    # ------------------------------------------------------------------
    #   Always executed hook method
    # ------------------------------------------------------------------
    def always_executed_hook(self):
        self.info_stream('In %s::always_executed_hook()' % self.get_name())
        self.state_machine()

    # ------------------------------------------------------------------
    #   ATTRIBUTES
    # ------------------------------------------------------------------
    def read_attr_hardware(self, data):
        pass

    # ------------------------------------------------------------------
    #   read Version attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_Version(self, the_att):
        the_att.set_value(self.mythen.version)

    def is_Version_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write  ReadoutBits attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_ReadoutBits(self, the_att):
        the_att.set_value(self.mythen.readoutbits)

    @ExceptionHandler
    def write_ReadoutBits(self, the_att):
        data = []
        the_att.get_write_value(data)
        if data[0] not in COUNTER_BITS:
            raise ValueError('Invalid value. %s' % repr(COUNTER_BITS))
        self.mythen.readoutbits = data[0]

    def is_ReadoutBits_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write RateCorrection attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_RateCorrection(self, the_att):
        the_att.set_value(self.mythen.rate)

    @ExceptionHandler
    def write_RateCorrection(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.rate = data[0]

    def is_RateCorrection_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write FlatFieldCorrection attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_FlatFieldCorrection(self, the_att):
        the_att.set_value(self.mythen.flatfield)

    @ExceptionHandler
    def write_FlatFieldCorrection(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.flatfield = data[0]

    def is_FlatFieldCorrection_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write BadChnInterp attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_BadChnInterp(self, the_att):
        the_att.set_value(self.mythen.badchnintrpl)

    @ExceptionHandler
    def write_BadChnInterp(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.badchnintrpl = data[0]

    def is_BadChnInterp_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read Settings attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_Settings(self, the_att):
        the_att.set_value(self.mythen.settings)

    def is_Settings_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write SettingsMode attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_SettingsMode(self, the_att):
        the_att.set_value(self.mythen.settingsmode)

    @ExceptionHandler
    def write_SettingsMode(self, the_att):
        data = []
        the_att.get_write_value(data)
        if data[0] not in SETTINGS_MODES:
            raise ValueError('Invalid value. %s' % repr(SETTINGS_MODES))

        self.async = True
        self.set_state(DEV_STATE_INIT)
        self.set_status('Configuring....')
        t = threading.Thread(target=self._setting_mode, args=[data[0]])
        t.start()

    def _setting_mode(self, value):
        self.mythen.settingsmode = value
        self.set_state(DEV_STATE_ON)
        self.async = False

    def is_SettingsMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write Tau attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_Tau(self, the_att):
        the_att.set_value(self.mythen.tau)

    @ExceptionHandler
    def write_Tau(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.tau = data[0]

    def is_Tau_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write IntTime attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_IntTime(self, the_att):
        the_att.set_value(self.mythen.inttime)

    @ExceptionHandler
    def write_IntTime(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.inttime = data[0]

    def is_Time_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write Frames attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_Frames(self, the_att):
        the_att.set_value(self.mythen.frames)

    @ExceptionHandler
    def write_Frames(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.frames = data[0]

    def is_Frames_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read RawData attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_RawData(self, the_att):
        the_att.set_value(self.raw_data)

    def is_LastRaw_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_MOVING)

    # ------------------------------------------------------------------
    #   read & write LiveMode attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_LiveMode(self, the_att):
        the_att.set_value(self.live_mode)

    @ExceptionHandler
    def write_LiveMode(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.live_mode = data[0]

    def is_LiveMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write LiveMode attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_LiveMode(self, the_att):
        the_att.set_value(self.live_mode)

    @ExceptionHandler
    def write_LiveMode(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.live_mode = data[0]

    def is_LiveMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write ROI attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_ROI(self, the_att):
        the_att.set_value(self.roi)

    @ExceptionHandler
    def write_ROI(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.roi = data[0:2]

    def is_ROI_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read ROIData attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_ROIData(self, the_att):
        the_att.set_value(self.roi_data)

    def is_ROIData_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_MOVING)

    # ------------------------------------------------------------------
    #   read & write Threshold attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_Threshold(self, the_att):
        the_att.set_value(self.mythen.threshold)

    @ExceptionHandler
    def write_Threshold(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.threshold = data[0]

    def is_Threshold_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   COMMANDS
    # ------------------------------------------------------------------
    @ExceptionHandler
    def _update_mask(self):
        # Take the bad channels
        self.mask = self.mythen.badchn

        # Apply the ROI
        min_roi, max_roi = self.roi
        self.mask[:min_roi] = 1
        self.mask[max_roi:] = 1

    @ExceptionHandler
    def Stop(self):
        self.stop_flag = True
        self.mythen.stop()

    def is_Stop_allowed(self):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_MOVING,)

    @ExceptionHandler
    def Start(self):
        self.raw_data = None
        self.buffer_raw = []
        self.buffer_roi = []
        self._update_mask()
        if self.live_mode:
            self.stop_flag = False
            method = self._livemode
            self.mythen.frames = 1
            self.set_state(DEV_STATE_MOVING)
            self.set_status('Live Mode')
            self.async = True
        else:
            method = self._acquisiton
            self.mythen.start()
        t = threading.Thread(target=method)
        t.start()


    def _acquisiton(self):
        while True:
            try:
                self.raw_data = self.mythen.readout
                new_data = np.ma.MaskedArray(self.raw_data, self.mask)
                self.roi_data = np.uint64(new_data.sum())
                self.push_change_event('RawData', self.raw_data)
                self.push_change_event('ROIData', self.roi_data)
                self.buffer_raw.append(self.raw_data)
                self.buffer_roi.append(self.roi_data)
            except MythenError:
                break

    def _livemode(self):
        while not self.stop_flag:
            try:
                self.mythen.start()
                self.raw_data = self.mythen.readout
                new_data = np.ma.MaskedArray(self.raw_data, self.mask)
                self.roi_data = np.uint64(new_data.sum())
                self.push_change_event('RawData', self.raw_data)
                self.push_change_event('ROIData', self.roi_data)
            except MythenError:
                break
        self.async = False

    def is_Start_allowed(self):
        return self.get_state() in (DEV_STATE_ON,)

    @ExceptionHandler
    def Reset(self):
        self.async = True
        self.set_state(DEV_STATE_INIT)
        self.set_status('Resetting....')
        t = threading.Thread(target=self._reset)
        t.start()

    def _reset(self):
        self.mythen.reset()
        self.set_state(DEV_STATE_ON)
        self.async = False

    def is_Reset_allowed(self):
        return self.get_state() in (DEV_STATE_MOVING, DEV_STATE_FAULT,
                                    DEV_STATE_UNKNOWN, DEV_STATE_ON)

    @ExceptionHandler
    def AutoSettings(self, value):
        self.async = True
        self.set_state(DEV_STATE_INIT)
        self.set_status('Configuring....')
        t = threading.Thread(target=self._autosettings, args=[value])
        t.start()

    def _autosettings(self, value):
        print value
        self.mythen.autosettings(value)
        self.set_state(DEV_STATE_ON)
        self.async = False

