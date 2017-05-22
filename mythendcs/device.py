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
import threading
import numpy as np
import time

from .core import Mythen, UDP_PORT, TCP_PORT, COUNTER_BITS, \
    SETTINGS_MODES, MythenError

DEV_STATE_UNKNOWN = PyTango.DevState.UNKNOWN
DEV_STATE_FAULT = PyTango.DevState.FAULT
DEV_STATE_RUNNING = PyTango.DevState.RUNNING
DEV_STATE_ON = PyTango.DevState.ON
DEV_STATE_INIT = PyTango.DevState.INIT



# Decorator for managing the exception
def ExceptionHandler(func):
    def new_func(*args, **kwargs):
        try:
            obj = args[0]
            obj.debug_stream('Entering in %s (%s)' % (func.__name__,
                                                      repr(args)))
            result = func(*args, **kwargs)
            obj.debug_stream('Exiting %s' % func.__name__)
            return result
        except Exception as e:
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
        'Port': [PyTango.DevString, 'TCP or UDP', 'UDP'],
        'NMod': [PyTango.DevLong, 'Number of modules connected', 1],
        'Timeout': [PyTango.DevLong, 'Serial port timeout', 3],
        'NROIs': [PyTango.DevLong, 'Number of ROIs', 3]
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
                        PyTango.AttrWriteType.READ, Mythen.MAX_CHANNELS]],
        'LiveMode': [[PyTango.ArgType.DevBoolean,
                      PyTango.AttrDataFormat.SCALAR,
                      PyTango.AttrWriteType.READ_WRITE]],
        'Threshold': [[PyTango.ArgType.DevDouble,
                       PyTango.AttrDataFormat.SCALAR,
                       PyTango.AttrWriteType.READ_WRITE],
                       {'min value': 0.05}],
        'ImageData': [[PyTango.ArgType.DevLong,
                       PyTango.AttrDataFormat.IMAGE,
                       PyTango.AttrWriteType.READ,
                       Mythen.MAX_CHANNELS, 30000]],
        'FramesReadies': [[PyTango.ArgType.DevULong64,
                           PyTango.AttrDataFormat.SCALAR,
                           PyTango.AttrWriteType.READ]],
        'TriggerMode': [[PyTango.ArgType.DevBoolean,
                         PyTango.AttrDataFormat.SCALAR,
                         PyTango.AttrWriteType.READ_WRITE]],
        'ContinuousTrigger': [[PyTango.ArgType.DevBoolean,
                         PyTango.AttrDataFormat.SCALAR,
                         PyTango.AttrWriteType.READ_WRITE]],
        'GateMode': [[PyTango.ArgType.DevBoolean,
                      PyTango.AttrDataFormat.SCALAR,
                      PyTango.AttrWriteType.READ_WRITE]],
        'OutputHigh': [[PyTango.ArgType.DevBoolean,
                        PyTango.AttrDataFormat.SCALAR,
                        PyTango.AttrWriteType.READ_WRITE]],
        'InputHigh': [[PyTango.ArgType.DevBoolean,
                       PyTango.AttrDataFormat.SCALAR,
                       PyTango.AttrWriteType.READ_WRITE]],


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
        except Exception as e:
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
        self.frames_readies = 0
        self.live_mode = False
        self.async = False
        self.raw_data = np.zeros(1280)
        self.image_data = []
        self.stop_flag = False
        self.roi_data = []
        self.rois = []
        for i in range(self.NROIs):
            data = 0
            rois = [0, Mythen.MAX_CHANNELS]
            self.roi_data.append(data)
            self.rois.append(rois)
        
        # Define events on attributes
        self.set_change_event('RawData', True, False)
        self.set_change_event('ReadoutBits', True, False)
        self.set_change_event('RateCorrection', True, False)
        self.set_change_event('FlatFieldCorrection', True, False)
        self.set_change_event('BadChnInterp', True, False)
        self.set_change_event('Settings', True, False)
        self.set_change_event('SettingsMode', True, False)
        self.set_change_event('Tau', True, False)
        self.set_change_event('IntTime', True, False)
        self.set_change_event('Frames', True, False)
        self.set_change_event('Threshold', True, False)
        self.set_change_event('LiveMode', True, False)
        self.set_change_event('State', True, False)
        self.set_change_event('Status', True, False)
        self.set_change_event('TriggerMode', True, False)
        self.set_change_event('GateMode', True, False)
        self.set_change_event('ContinuousTrigger', True, False)
        self.set_change_event('OutputHigh', True, False)
        self.set_change_event('InputHigh', True, False)

        self.dyn_attr()

    # ------------------------------------------------------------------
    #   Create dynamic attributes
    # ------------------------------------------------------------------
    def dyn_attr(self):
        attr_roilow_name = 'ROI{0}Low'
        attr_roihigh_name = 'ROI{0}High'
        attr_roidata_name = 'ROI{0}Data'
        
        for roi in range(1, self.NROIs+1):
            #ROI result
            attr_roidata = PyTango.Attr(attr_roidata_name.format(roi),
                                        PyTango.ArgType.DevULong64,
                                        PyTango.AttrWriteType.READ)

            self.add_attribute(attr_roidata, self.read_ROIData, None,
                               self.is_ROIData_allowed)
           
            #Low value of the ROI
            attr_roilow = PyTango.Attr(attr_roilow_name.format(roi),
                                       PyTango.ArgType.DevULong,
                                       PyTango.AttrWriteType.READ_WRITE)
            props = PyTango.UserDefaultAttrProp()
            props.set_max_value(str(Mythen.MAX_CHANNELS - 1))
            props.set_min_value('0')
            attr_roilow.set_default_properties(props)

            self.add_attribute(attr_roilow, self.read_ROILow, self.write_ROILow,
                               self.is_ROILow_allowed)
            
            attr_roihigh = PyTango.Attr(attr_roihigh_name.format(roi),
                                        PyTango.ArgType.DevULong,
                                        PyTango.AttrWriteType.READ_WRITE)
                                        
            
            props.set_max_value(str(Mythen.MAX_CHANNELS))
            props.set_min_value('1')
            attr_roihigh.set_default_properties(props)

            self.add_attribute(attr_roihigh, self.read_ROIHigh,
                               self.write_ROIHigh, self.is_ROIHigh_allowed)
           
            self.set_change_event(attr_roilow_name.format(roi), True, False)
            self.set_change_event(attr_roihigh_name.format(roi), True, False)
            self.set_change_event(attr_roidata_name.format(roi), True, False)

    
    # ------------------------------------------------------------------
    #   State machine implementation
    # ------------------------------------------------------------------
    @ExceptionHandler
    def state_machine(self):
        if self.async:
            return
        status = self.mythen.status
        if status in ['RUNNING', 'WAIT_TRIGGER']:
            self.set_state(DEV_STATE_RUNNING)
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
        self.push_change_event('State', self.get_state())
        self.push_change_event('Status', self.get_status())

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
        self.push_change_event('ReadoutBits', data[0])

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
        self.push_change_event('RateCorrection', data[0])

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
        self.push_change_event('FlatFieldCorrection', data[0])

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
        self.push_change_event('BadChnInterp', data[0])

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
        settings = self.mythen.settings
        self.push_change_event('Settings', settings)
        self.push_change_event('SettingsMode', value)
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
        self.push_change_event('Tau', data[0])

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
        self.push_change_event('IntTime', data[0])

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
        self.push_change_event('Frames', data[0])

    def is_Frames_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read RawData attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_RawData(self, the_att):
        the_att.set_value(self.raw_data)

    def is_LastRaw_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING)

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
        self.push_change_event('LiveMode', data[0])

    def is_LiveMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING)

    # ------------------------------------------------------------------
    #   read & write TriggerMode attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_TriggerMode(self, the_att):
        the_att.set_value(self.mythen.triggermode)

    @ExceptionHandler
    def write_TriggerMode(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.triggermode = data[0]
        self.push_change_event('TriggerMode', data[0])

    def is_TriggerMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write ContinuousTrigger attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_ContinuousTrigger(self, the_att):
        the_att.set_value(self.mythen.continuoustrigger)

    @ExceptionHandler
    def write_ContinuousTrigger(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.continuoustrigger = data[0]
        self.push_change_event('ContinuousTrigger', data[0])

    def is_ContinuousTrigger_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write GateMode attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_GateMode(self, the_att):
        the_att.set_value(self.mythen.gatemode)

    @ExceptionHandler
    def write_GateMode(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.gatemode = data[0]
        self.push_change_event('GateMode', data[0])

    def is_GateMode_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write OutputHigh attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_OutputHigh(self, the_att):
        the_att.set_value(self.mythen.outputhigh)

    @ExceptionHandler
    def write_OutputHigh(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.outputhigh = data[0]
        self.push_change_event('OutputHigh', data[0])

    def is_OutputHigh_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write InputHigh attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_InputHigh(self, the_att):
        the_att.set_value(self.mythen.inputhigh)

    @ExceptionHandler
    def write_InputHigh(self, the_att):
        data = []
        the_att.get_write_value(data)
        self.mythen.inputhigh = data[0]
        self.push_change_event('InputHigh', data[0])

    def is_InputHigh_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write ROILow attribute
    # ------------------------------------------------------------------
    #@ExceptionHandler
    def read_ROILow(self, the_att):
        attr_name = the_att.get_name()
        nroi = int(attr_name[3]) - 1
        the_att.set_value(self.rois[nroi][0])

    #@ExceptionHandler
    def write_ROILow(self, the_att):
        data = []
        attr_name = the_att.get_name()
        nroi = int(attr_name[3]) - 1
        the_att.get_write_value(data)
        if data[0] >= self.rois[nroi][1]:
            raise ValueError('The value should be lower than the ROIHigh.')
        self.rois[nroi][0] = data[0]
        self.push_change_event(attr_name, data[0])

    def is_ROILow_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read & write ROILow attribute
    # ------------------------------------------------------------------
    #@ExceptionHandler
    def read_ROIHigh(self, the_att):
        attr_name = the_att.get_name()
        nroi = int(attr_name[3]) - 1
        the_att.set_value(self.rois[nroi][1])

    #@ExceptionHandler
    def write_ROIHigh(self, the_att):
        data = []
        the_att.get_write_value(data)
        attr_name = the_att.get_name()
        nroi = int(attr_name[3]) - 1
        if data[0] <= self.rois[nroi][0]:
            raise ValueError('The value should be greater than the ROILow.')
        self.rois[nroi][1] = data[0]
        self.push_change_event(attr_name, data[0])

    def is_ROIHigh_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read ROIData attribute
    # ------------------------------------------------------------------
    #@ExceptionHandler
    def read_ROIData(self, the_att):
        attr_name = the_att.get_name()
        nroi = int(attr_name[3]) - 1
        the_att.set_value(self.roi_data[nroi])

    def is_ROIData_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING)

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
        self.push_change_event('Threshold', data[0])

    def is_Threshold_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON,)

    # ------------------------------------------------------------------
    #   read Image attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_ImageData(self, the_att):
        the_att.set_value(self.image_data)

    def is_ImageData_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING)

    # ------------------------------------------------------------------
    #   read FramesReadies attribute
    # ------------------------------------------------------------------
    @ExceptionHandler
    def read_FramesReadies(self, the_att):
        the_att.set_value(self.frames_readies)

    def is_FramesReadies_allowed(self, req_type):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING)

    # ------------------------------------------------------------------
    #   COMMANDS
    # ------------------------------------------------------------------
    @ExceptionHandler
    def _get_hwmask(self):
        # Take the bad channels
        return self.mythen.badchn

    @ExceptionHandler
    def _roi2mask(self, nroi, mask):
        new_mask = np.array(mask)
        min_roi, max_roi = self.rois[nroi]
        new_mask[:min_roi] = 1
        new_mask[max_roi:] = 1
        return new_mask

    @ExceptionHandler
    def Stop(self):
        self.stop_flag = True
        self.mythen.stop()

    def is_Stop_allowed(self):
        return self.get_state() in (DEV_STATE_ON, DEV_STATE_RUNNING,)

    @ExceptionHandler
    def Start(self):
        self.raw_data = None
        hw_mask = self._get_hwmask()
        self.masks = []
        self.image_data = []
        self.frames_readies = 0
        for i in range(self.NROIs):
            self.masks.append(self._roi2mask(i, hw_mask))
        
        self.async = True
        if self.live_mode:
            self.stop_flag = False
            method = self._livemode
            self.mythen.frames = 1
            self.set_status('Live Mode')
        else:
            if not self.mythen.triggermode:
                method = self._frame_acq
                self.set_status('Acquisition Mode: Internal Trigger')
                #self.mythen.start()
            else:
                method = self._multiframes_acq
                self.set_status('Acquisition Mode: External Trigger')
            self.mythen.start()    
        t = threading.Thread(target=method)
        t.start()
        self.set_state(DEV_STATE_RUNNING)
        self.push_change_event('State', self.get_state())
        self.push_change_event('Status', self.get_status())
        
    def _acq(self):
        print ('acquisition thread')
        self.raw_data = self.mythen.readout
        self.push_change_event('RawData', self.raw_data)
        self.image_data.append(self.raw_data.tolist())
        for i in range(self.NROIs):
            new_data = np.ma.MaskedArray(self.raw_data, self.masks[i])
            self.roi_data[i] = np.uint64(new_data.sum())
            print self.roi_data[i]
            attr_name = 'ROI%dData' % (i+1)
            self.push_change_event(attr_name, self.roi_data[i])

    def _acq_end(self):
        self.set_state(DEV_STATE_ON)
        self.set_status('ON')
        self.push_change_event('State', self.get_state())
        self.push_change_event('Status', self.get_status())
        self.async = False

    def _multiframes_acq(self):

        while True:
            while self.mythen.fifoempty and self.mythen.running:
                time.sleep(0.1)
            try:
                self.raw_data = self.mythen.readout
                self.push_change_event('RawData', self.raw_data)
                self.image_data.append(self.raw_data.tolist())
                self.frames_readies += 1
            except MythenError as e:
                print 'error!!!!!!!!!!!!!!!!!!!!!!11\n\n', e
                break
        self._acq_end()

    def _frame_acq(self):
        while True:
            try:
                self._acq()
            except MythenError:
                break
        self._acq_end()

    def _livemode(self):
        while not self.stop_flag:
            try:
                self.mythen.start()
                self._acq()
            except MythenError:
                break
        self._acq_end()

    def is_Start_allowed(self):
        return self.get_state() in (DEV_STATE_ON,)

    @ExceptionHandler
    def Reset(self):
        self.async = True
        self.set_state(DEV_STATE_INIT)
        self.set_status('Resetting....')
        self.push_change_event('State', self.get_state())
        self.push_change_event('Status', self.get_status())
        t = threading.Thread(target=self._reset)
        t.start()

    def _reset(self):
        self.mythen.reset()
        self.push_change_event('ReadoutBits', self.mythen.readoutbits)
        self.push_change_event('RateCorrection', self.mythen.rate)
        self.push_change_event('FlatFieldCorrection', self.mythen.flatfield)
        self.push_change_event('BadChnInterp', self.mythen.badchnintrpl)
        self.push_change_event('Settings', self.mythen.settings)
        self.push_change_event('SettingsMode', self.mythen.settingsmode)
        self.push_change_event('Tau', self.mythen.tau)
        self.push_change_event('IntTime', self.mythen.inttime)
        self.push_change_event('Frames', self.mythen.frames)
        self.push_change_event('Threshold', self.mythen.threshold)
        self.push_change_event('LiveMode', self.live_mode)
        self.set_state(DEV_STATE_ON)
        self.set_status('ON')
        self.push_change_event('State', self.get_state())
        self.push_change_event('Status', self.get_status())
        self.async = False

    def is_Reset_allowed(self):
        return self.get_state() in (DEV_STATE_RUNNING, DEV_STATE_FAULT,
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
        settings = self.mythen.settings
        settings_mode = self.mythen.settingsmode
        self.push_change_event('Settings', settings)
        self.push_change_event('SettingsMode', settings_mode)
        self.set_state(DEV_STATE_ON)
        self.async = False
