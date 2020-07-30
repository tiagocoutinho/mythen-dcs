import time

import numpy
import pytest

from mythendcs.core import (
    Mythen, MythenError, ERR_MYTHEN_BAD_PARAMETER, ERRORS,
    UDP, TCP, UDP_PORT, TCP_PORT, COUNTER_BITS
)

tcp_udp_conn = pytest.mark.parametrize(
    "conn", [TCP, UDP], ids=['tcp', 'udp'], indirect=True
)

tcp_udp = pytest.mark.parametrize(
    "mythen", [TCP, UDP], ids=['tcp', 'udp'], indirect=True
)


@tcp_udp_conn
def test_creation(conn):
    mythen = Mythen(conn)
    serv_mythen = conn.server.mythen
    assert serv_mythen.config['commandid'] == 6
    assert serv_mythen.config['commandsetid'] == 6


@tcp_udp
def test_queries(mythen):
    config = mythen.server.mythen.config
    nmods = config["nmodules"]
    ff = numpy.array(config["flatfield"][:nmods * 1280], dtype=numpy.int32)
    badch = numpy.array(config["badchannels"][:nmods * 1280], dtype=numpy.int32)
    assert mythen.version == config["version"][:-1] # take out \x00
    assert mythen.frames == config["frames"]
    assert mythen.inttime == int(config["time"] * 1E-7)
    assert mythen.settings == "Standard"
    assert mythen.settingsmode == config["settingsmode"]
    assert mythen.readoutbits == config["nbits"]
    assert mythen.status == "ON"
    assert not mythen.waitingtrigger
    assert mythen.fifoempty
    assert not mythen.running
    assert mythen.badchnintrpl == config["badchannelinterpolation"]
    assert mythen.flatfield == config["flatfieldcorrection"]
    assert (mythen.flatfieldconf == ff).all()
    assert (mythen.badchn == badch).all()
    assert mythen.rate == config["ratecorrection"]
    assert mythen.get_active_modules() == config["nmodules"]
    assert mythen.triggermode == bool(config["trigen"])
    assert mythen.continuoustrigger == bool(config["conttrigen"])
    assert mythen.gatemode == bool(config["gateen"])

    # TODO fix in the core: value is per module
#    assert mythen.tau == config["tau"][:nmods]
#    assert mythen.threshold == config["kthresh"]


@tcp_udp
def test_commands(mythen):
    config = mythen.server.mythen.config

    mythen.readoutbits = 8
    assert config["nbits"] == 8

    mythen.badchnintrpl = True
    assert config["badchannelinterpolation"] == 1

    mythen.rate = True
    assert config["ratecorrection"] == 1

    mythen.flatfield = True
    assert config["flatfieldcorrection" ] == 1

    mythen.set_delay_trigger(0.101)
    assert config["delbef"] == 1_010_000

    mythen.set_delay_frame(0.51)
    assert config["delafter"] == 5_100_000

    mythen.set_num_gates(5)
    assert config["gates"] == 5

    mythen.set_active_modules(1)
    assert config["nmodules"] == 1


def test_command_bad_parameter(tcp_conn):
    mythen = Mythen(tcp_conn)

    err_code = ERR_MYTHEN_BAD_PARAMETER
    err_msg = ERRORS[err_code]

    pars = (("readoutbits", 9), ("badchnintrpl", "yes"),
            ("rate", "true"), ("flatfield", 1), ("triggermode", "Y"),
            ("continuoustrigger", "y"), ("gatemode", 0))
    for attr, value in pars:
        with pytest.raises(MythenError) as err:
            setattr(mythen, attr, value)
        assert err.value.errcode == err_code
        assert str(err.value) == "Error {}: {}".format(err_code, err_msg)
        assert repr(err.value) == "MythenError({}, {!r})".format(err_code, err_msg)


def test_error(tcp_conn):
    mythen = Mythen(tcp_conn)
    err_code = ERR_MYTHEN_BAD_PARAMETER
    err_msg = ERRORS[err_code]
    with pytest.raises(MythenError) as err:
        mythen.badchnintrpl = "yes"
    assert err.value.errcode == err_code
    assert str(err.value) == "Error {}: {}".format(err_code, err_msg)
    assert repr(err.value) == "MythenError({}, {!r})".format(err_code, err_msg)


@tcp_udp
@pytest.mark.slow
def test_reset(mythen):
    mythen.reset()


@tcp_udp
def test_readout(mythen):
    mythen.frames = 1
    mythen.inttime = 0.1
    mythen.start()
    assert mythen.status == "RUNNING"
    assert mythen.running
    assert mythen.fifoempty
    time.sleep(0.1)
    assert mythen.status == "ON"
    assert not mythen.running
    assert not mythen.fifoempty
    frame = mythen.readout
    assert mythen.fifoempty
    nmods = mythen.server.mythen.config["nmodules"]
    assert (frame == numpy.full(1280 * nmods, 0, dtype="<i4")).all()


@tcp_udp
@pytest.mark.parametrize("frames,inttime", [(5, 0.1), (500, 0.01)])
@pytest.mark.slow
def test_readout_n(mythen, frames, inttime):
    nmods = mythen.server.mythen.config["nmodules"]
    mythen.frames = frames
    mythen.inttime = inttime
    mythen.start()
    start_time = time.time()
    assert mythen.status == "RUNNING"
    assert mythen.running
    assert mythen.fifoempty
    for i in range(frames):
        frame = mythen.readout
        assert (frame == numpy.full(1280 * nmods, i, dtype="<i4")).all()
    dt = time.time() - start_time
    assert pytest.approx(dt, rel=0.1) == frames * inttime
    assert mythen.status == "ON"
    assert mythen.fifoempty


@tcp_udp
def test_readout_into(mythen):
    mythen.frames = 1
    mythen.inttime = 0.1
    mythen.start()
    assert mythen.status == "RUNNING"
    assert mythen.running
    assert mythen.fifoempty
    time.sleep(0.1)
    assert mythen.status == "ON"
    assert not mythen.running
    assert not mythen.fifoempty
    nmods = mythen.server.mythen.config["nmodules"]
    buff = numpy.full(1280 * nmods, 333, dtype="<i4")
    frame = mythen.readout_into(buff)
    assert mythen.fifoempty
    assert buff is frame
    assert (frame == numpy.full(1280 * nmods, 0, dtype="<i4")).all()


@tcp_udp
@pytest.mark.parametrize("frames,inttime", [(5, 0.1), (500, 0.01)])
@pytest.mark.slow
def test_ireadout_n(mythen, frames, inttime):
    nmods = mythen.server.mythen.config["nmodules"]
    mythen.frames = frames
    mythen.inttime = inttime
    mythen.start()
    start_time = time.time()
    assert mythen.status == "RUNNING"
    assert mythen.running
    assert mythen.fifoempty
    for i, frame, block in mythen.ireadout(frames):
        expected = numpy.full(1280 * nmods, i, dtype="<i4")
        assert (frame == expected).all()
        assert (block[i] == expected).all()
    dt = time.time() - start_time
    assert pytest.approx(dt, rel=0.1) == frames * inttime


@tcp_udp
def test_stop(mythen):
    mythen.frames = 100
    mythen.inttime = 10
    mythen.start()
    assert mythen.status == "RUNNING"
    assert mythen.running
    assert mythen.fifoempty
    mythen.stop()
    assert mythen.status == "ON"
    assert not mythen.running
    assert not mythen.fifoempty
