import time

import pytest

from mythendcs.core import TCP, UDP

try:
    import Lima
    from Lima.Core import CtControl, AcqRunning
    from mythendcs.lima.camera import Interface
except ImportError:
    Lima = None


tcp_udp = pytest.mark.parametrize(
    "mythen", [TCP, UDP], ids=['tcp', 'udp'], indirect=True
)

skip_if_no_lima = pytest.mark.skipif(Lima is None, reason="Lima not installed")


@tcp_udp
@skip_if_no_lima
def test_creation(mythen):
    interface = Interface(mythen)
    ctrl = CtControl(interface)
    assert ctrl is not None


@tcp_udp
@pytest.mark.parametrize("frames,inttime", [(5, 0.1), (500, 0.01)])
@pytest.mark.slow
@skip_if_no_lima
def test_acquisition(mythen, frames, inttime):
    total_time = frames * inttime
    timeout = total_time + 1
    interface = Interface(mythen)
    ctrl = CtControl(interface)
    acq = ctrl.acquisition()
    acq.setAcqNbFrames(frames)
    acq.setAcqExpoTime(inttime)
    ctrl.prepareAcq()
    ctrl.startAcq()
    start_time = time.time()
    status = ctrl.getStatus().AcquisitionStatus
    assert status == AcqRunning
    while status == AcqRunning and timeout > 0:
        time.sleep(0.01)
        timeout -= 0.01
        status = ctrl.getStatus().AcquisitionStatus
    dt = time.time() - start_time
    assert status != AcqRunning
    assert pytest.approx(dt, rel=0.1) == total_time

