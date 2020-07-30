import time
import logging
import threading

import numpy

from Lima.Core import (
    HwInterface, HwDetInfoCtrlObj, HwSyncCtrlObj, HwBufferCtrlObj, HwCap,
    HwFrameInfoType, SoftBufferCtrlObj, Size, FrameDim, Bpp32,
    Timestamp, AcqReady, AcqRunning, CtControl, CtSaving,
    IntTrig, ExtTrigSingle, ExtTrigMult, ExtGate)

from ..core import Mythen, Connection, TCP_PORT


Status = HwInterface.StatusType


class Sync(HwSyncCtrlObj):

    trig_mode = IntTrig

    def __init__(self, detector):
        self.detector = detector
        super().__init__()

    def checkTrigMode(self, trig_mode):
        return trig_mode in {IntTrig, ExtTrigSingle, ExtTrigMult, ExtGate}

    def setTrigMode(self, trig_mode):
        if not self.checkTrigMode(trig_mode):
            raise ValueError('Unsupported trigger mode')
        if trig_mode == IntTrig:
            self.detector.triggermode = False
            self.detector.continuoustrigger = False
            self.detector.gatemode = False
        elif trig_mode == ExtTrigSingle:
            self.detector.triggermode = True
            self.detector.continuoustrigger = False
            self.detector.gatemode = False
        elif trig_mode == ExtTrigMult:
            self.detector.triggermode = True
            self.detector.continuoustrigger = True
            self.detector.gatemode = False
        elif trig_mode == ExtGate:
            self.detector.gatemode = True

    def getTrigMode(self):
        if self.detector.gatemode:
            return ExtGate
        elif self.detector.triggermode:
            return ExtTrigMult if self.detector.continuoustrigger else ExtTrigSingle
        return IntTrig

    def setExpTime(self, exp_time):
        self.detector.inttime = exp_time

    def getExpTime(self):
        return self.detector.inttime

    def setLatTime(self, lat_time):
        self.detector.set_delay_frame(lat_time)
        self.latency_time = lat_time

    def getLatTime(self):
        return self.latency_time

    def setNbHwFrames(self, nb_frames):
        self.detector.frames = nb_frames

    def getNbHwFrames(self):
        return self.detector.frames

    def getValidRanges(self):
        return self.ValidRangesType(10E-9, 1E6, 10E-9, 1E6)


class DetInfo(HwDetInfoCtrlObj):

    image_type = Bpp32
    max_image_size = Size(1280 * 24, 1)

    def __init__(self, detector):
        self.detector = detector
        super().__init__()

    def getMaxImageSize(self):
        return Size(self.detector.get_active_modules() * 1280, 1)

    def getDetectorImageSize(self):
        return Size(self.detector.get_active_modules() * 1280, 1)

    def getDefImageType(self):
        return type(self).image_type

    def getCurrImageType(self):
        return self.image_type

    def setCurrImageType(self, image_type):
        if image_type != self.image_type:
            raise ValueError("unsupported detector image type")

    def getPixelSize(self):
        return (50.0, 50.0)

    def getDetectorType(self):
        return "Mythen2"

    def getDetectorModel(self):
        return self.detector.version

    def registerMaxImageSizeCallback(self, cb):
        pass

    def unregisterMaxImageSizeCallback(self, cb):
        pass


class Acquisition:

    def __init__(self, detector, buffer_manager, nb_frames, frame_dim):
        self.detector = detector
        self.buffer_manager = buffer_manager
        self.nb_frames = nb_frames
        self.frame_dim = frame_dim
        self.nb_acquired_frames = 0
        self.status = Status.Ready
        self.frame_infos = [HwFrameInfoType() for i in range(nb_frames)]
        self.stopped = False
        self.acq_thread = threading.Thread(target=self.acquire)

    def start(self):
        self.acq_thread.start()

    def stop(self):
        self.detector.stop()
        self.stopped = True
        self.acq_thread.join()

    def acquire(self):
        detector, buff_mgr = self.detector, self.buffer_manager
        frame_infos = self.frame_infos
        frame_size = self.frame_dim.getMemSize()
        start_time = time.time()
        detector.start()
        self.status = Status.Exposure
        buff_mgr.setStartTimestamp(Timestamp(start_time))
        for frame_nb in range(self.nb_frames):
            if self.stopped:
                break
            self.status = Status.Readout
            buff = buff_mgr.getFrameBufferPtr(frame_nb)
            # don't know why the sip.voidptr has no size
            buff.setsize(frame_size)
            data = numpy.frombuffer(buff, dtype='<i4')
            detector.readout_into(data)
            frame_info = frame_infos[frame_nb]
            frame_info.acq_frame_nb = frame_nb
            buff_mgr.newFrameReady(frame_info)
            self.nb_acquired_frames += 1
            self.status = Status.Exposure
        self.status = Status.Ready


class Interface(HwInterface):

    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.det_info = DetInfo(detector)
        self.sync = Sync(detector)
        self.buff = SoftBufferCtrlObj()
        self.caps = list(map(HwCap, (self.det_info, self.sync, self.buff)))
        self.acq = None

    def getCapList(self):
        return self.caps

    def reset(self, reset_level):
        pass

    def prepareAcq(self):
        nb_frames = self.sync.getNbHwFrames()
        frame_dim = self.buff.getFrameDim()
        buffer_manager = self.buff.getBuffer()
        self.acq = Acquisition(self.detector, buffer_manager, nb_frames, frame_dim)

    def startAcq(self):
        self.acq.start()

    def stopAcq(self):
        if self.acq:
            self.acq.stop()

    def getStatus(self):
        s = Status()
        s.set(self.acq.status if self.acq else Status.Ready)
        return s

    def getNbHwAcquiredFrames(self):
        return self.acq.nb_acquired_frames if self.acq else 0

