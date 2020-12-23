"""
Configure a mythen detector in a YAML file:

.. code-block:: yaml

    devices:
    - class: Mythen2
      package: mythendcs.simulator
      transports:
      - type: udp
        url: :1030
      - type: tcp
        url: :1031

And start the simulator with::

    $ sinstruments-server -c mythen.yml

A simple *nc* client can be used to connect to the instrument (`-I 1` disables
the input buffer since the protocol replies are a binary without terminator)::

    $ nc -I 1 0 1031
    -get version


An input trigger can be simulated by configuring a TCP socket

.. code-block:: yaml

    devices:
    - class: Mythen2
      package: mythendcs.simulator
      transports:
      - type: udp
        url: :1030
      - type: tcp
        url: :1031
      trigger:
        in: :10310

The input trigger socket listens for "trigger\n", "low\n" and "high\n" messages.

Example on how to acquire 10 frames with 1.1s exposure time with trigger start::

    $ nc 0 1031
    -frames 10
    -time 11000000
    -trigen 1
    -start

At this point the simulator acquisition is armed and ready to receive a trigger
to start acquisition. The trigger can be sent with::

    $ nc 0 10310
    trigger
"""

import time
import struct
import logging
import collections

import gevent.event
import gevent.queue
import gevent.socket

from sinstruments.simulator import BaseDevice, MessageProtocol

ns100 = 1E-7

Type = collections.namedtuple("Type", "name encode decode default")


def _Type(name, decoder=int, type="i", default=None):
    def encode(ctx):
        return struct.pack("<{}".format(type), ctx[name])

    def decode(ctx, value):
        ctx[name] = value = decoder(value)
        return value

    return Type(name, encode, decode, default)


def Str(name, default=None):
    def encode(ctx):
        return ctx[name].encode()

    def decode(ctx):
        ctx[name] = value = value.decode()
        return value

    return Type(name, encode, decode, default)


def Int(name, default=None):
    return _Type(name, int, "i", default=default)


def Long(name, default=None):
    return _Type(name, int, "q", default=default)


def Float(name, default=None):
    return _Type(name, float, "f", default=default)


def _TypeArrayNMod(name, decoder=int, type="i", default=None):
    def encode(ctx):
        n, v = ctx["nmodules"], ctx[name]
        return struct.pack("<{}{}".format(n, type), *v[:n])

    def decode(ctx, value):
        v = [decoder(i) for i in value]

    return Type(name, encode, decode, default)


def IntArrayNMod(name, default=None):
    return _TypeArrayNMod(name, int, "i", default=default)


def FloatArrayNMod(name, default=None):
    return _TypeArrayNMod(name, float, "f", default=default)


def _TypeArrayNChan(name, decoder=int, type="i", default=None):
    def encode(ctx):
        nb_mod, nb_ch, v = ctx["nmodules"], ctx["modchannels"], ctx[name]
        n = nb_mod * nb_ch
        return struct.pack("<{}{}".format(n, type), *v[:n])

    def decode(ctx, value):
        v = [decoder(i) for i in value]

    return Type(name, encode, decode, default)


def IntArrayNChan(name, default=None):
    return _TypeArrayNChan(name, int, "i", default=default)


TYPES = (
    Str("assemblydate", "2020-07-28" + 40 * "\x00"),
    IntArrayNChan("badchannels", 4 * 1280 * [0]),
    Int("commandid", 0),
    Int("commandsetid", 0),
    Float("dcstemperature", 307.896),
    Float("frameratemax", 987.5),
    Str("fwversion", "01.03.06\x00"),
    FloatArrayNMod("humidity", [13.4, 12.1, 17.9, 11.8]),
    IntArrayNMod("hv", [124, 122, 178, 124]),
    Int("modchannels", 1280),
    Str("modfwversion", 4 * "01.03.07" + "\x00"),
    IntArrayNMod("modnum", [48867, 48868, 48869, 48870]),
    Int("module", 65535),
    Int("nmaxmodules", 4),
    Int("nmodules", 4),
    IntArrayNMod("sensormaterial", [0, 0, 0, 0]),
    IntArrayNMod("sensorthickness", [23, 65, 128, 40]),
    IntArrayNMod("sensorwidth", [678, 432, 4342, 3232]),
    Int("systemnum", 893278),
    FloatArrayNMod("temperature", [308.32, 310.323, 305.4927, 302.4483]),
    Str("testversion", "simula\x00"),
    Str("version", "M4.0.1\x00"),
    Long("time", 10_000_000),
    Int("nbits", 24),
    Int("frames", 1),
    Int("conttrigen", 0),
    Int("gateen", 0),
    Int("gates", 1),
    Int("delbef", 0),
    Int("delafter", 0),
    Int("trigen", 0),
    Int("ratecorrection", 0),
    Int("flatfieldcorrection", 0),
    Int("badchannelinterpolation", 0),
    IntArrayNChan("flatfield", 4 * 1280 * [0]),
    Int("inpol", 0),  # 0 - rising edge, 1 - falling edge (removed in v4.0)
    Int("outpol", 0),  # 0 - rising edge, 1 - falling edge (removed in v4.0)
    IntArrayNMod(
        "settings", 4 * [0]
    ),  # 0: Standard, 1: Highgain, 2: Fast, 3: Unknown (deprecated since v3.0)
    Str("settingsmode", "auto 5600 11200"),   # (deprecated since v3.0)
    FloatArrayNMod("tau", [4.6, 8.7, 7.4, 2.1]),
    FloatArrayNMod("kthresh", 4 * [6.4]),
    FloatArrayNMod("kthreshmin", 4 * [0.05]),
    FloatArrayNMod("kthreshmax", 4 * [69.56]),
    FloatArrayNMod("energy", 4 * [8.05]),
    FloatArrayNMod("energymin", 4 * [0.05]),
    FloatArrayNMod("energymax", 4 * [69.56]),
)

TYPE_MAP = {t.name: t for t in TYPES}


OK = 4 * b"\x00"


class Protocol(MessageProtocol):
    def read_messages(self):
        transport = self.transport
        while True:
            data = transport.read(self.channel, size=4096)
            if not data:
                return
            yield data


class BaseAcquisition:
    def __init__(
        self, signal, log, nb_frames, exposure_time, nb_channels, delay_before, delay_after, gates
    ):
        self.name = type(self).__name__
        self.signal = signal
        self.nb_frames = nb_frames
        self.exposure_time = exposure_time
        self.nb_channels = nb_channels
        self.delay_before = delay_before
        self.delay_after = delay_after
        self.nb_gates = gates
        self.finished = None
        self.exposing = False
        self.buffer = gevent.queue.Queue()
        self._log = log.getChild(self.name)

    def run(self):
        self.finished = False
        frame_nb = -1
        self._log.info("Start acquisition")
        try:
            with self.signal:
                for frame_nb, frame in enumerate(self.steps()):
                    self.buffer.put(frame)
        except gevent.GreenletExit:
            if frame_nb < (self.nb_frames - 1):
                frame = self.create_frame(frame_nb+1)
                self.buffer.put(frame)
            self.buffer.put(None)
        finally:
            self.finished = True
            self._log.info("Finished acquisition")

    def steps(self):
        for frame_nb in range(self.nb_frames):
            yield self.acquire(frame_nb)

    def create_frame(self, frame_nb, exposure_time):
        return self.nb_channels * frame_nb.to_bytes(4, 'little', signed=True)

    def expose(self, frame_nb):
        self.exposing = True
        self._log.debug("start exposure %d/%d...", frame_nb + 1, self.nb_frames)
        self.signal.gate_high()
        gevent.sleep(self.exposure_time)
        self.signal.gate_low()
        self.exposing = False
        self._log.debug("finished exposure %d/%d...", frame_nb + 1, self.nb_frames)
        return self.exposure_time

    def acquire(self, frame_nb):
        self._log.debug("start acquiring %d/%d...", frame_nb + 1, self.nb_frames)
        gevent.sleep(self.delay_before)
        t = self.expose(frame_nb)
        gevent.sleep(self.delay_after)
        frame = self.create_frame(frame_nb, t)
        self._log.debug("finished acquiring %d/%d...", frame_nb + 1, self.nb_frames)
        return frame

    def trigger(self):
        self._log.warn("trigger ignored")

    def gate_high(self):
        self._log.warn("gate high ignored")

    def gate_low(self):
        self._log.warn("gate low ignored")


class InternalAcquisition(BaseAcquisition):
    pass


class BaseTriggerAcquisition(BaseAcquisition):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._trigger = gevent.event.Event()

    def trigger(self):
        if self._trigger is None:
            self._log.warn("trigger ignored")
        else:
            self._log.debug("trigger!")
            self._trigger.set()

    def wait_for_trigger(self):
        self._trigger.wait()
        self._trigger = None
        if self.delay_before > 0:
            gevent.sleep(self.delay_before)


class SingleTriggerAcquisition(BaseTriggerAcquisition):
    def steps(self):
        self.wait_for_trigger()
        for frame_nb in range(self.nb_frames):
            yield self.acquire(frame_nb)


class ContinuousTriggerAcquisition(BaseTriggerAcquisition):
    def steps(self):
        for frame_nb in range(self.nb_frames):
            self.wait_for_trigger()
            yield self.acquire(frame_nb)
            if frame_nb < self.nb_frames - 1:
                self._trigger = gevent.event.Event()


class GateAcquisition(BaseAcquisition):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gate_high = gevent.event.Event()
        self._gate_low = gevent.event.Event()

    def gate_high(self):
        self._gate_high.set()

    def gate_low(self):
        self._gate_low.set()

    def wait_high(self):
        self._gate_high.wait()
        self._gate_high.clear()

    def wait_low(self):
        self._gate_low.wait()
        self._gate_low.clear()

    def expose(self, frame_nb):
        gate_nb = 0
        exposure_time = 0
        nb_frames, nb_gates = self.nb_frames, self.nb_gates
        while gate_nb < nb_gates:
            self.wait_high()
            self.exposing = True
            start = time.time()
            self.signal.gate_high()
            self._log.debug("start exposure %d/%d (gate %d/%d)...",
                            frame_nb + 1, nb_frames, gate_nb, nb_gates)
            self.wait_low()
            self.signal.gate_low()
            self.exposing = False
            exposure_time += time.time() - start
            self._log.debug("finished exposure %d/%d (gate %d/%d)",
                            frame_nb + 1, nb_frames, gate_nb, nb_gates)
            gate_nb += 1
        return exposure_time


def start_acquisition(config, signal, log):
    gate_enabled = config["gateen"]
    trigger_enabled = config["trigen"]
    continuous_trigger = config["conttrigen"]
    hardware_trigger = gate_enabled or trigger_enabled or continuous_trigger_enabled
    internal_trigger = not hardware_trigger
    # internal trigger does not support delay before frame (<=> delay after trigger)
    delay_before = config["delbef"] * ns100 if hardware_trigger else 0
    delay_after = config["delafter"] * ns100
    exp_time = config["time"] * ns100
    nb_channels = config["nmodules"] * config["modchannels"]
    nb_gates = config["gates"] if gate_enabled else 1
    nb_frames = config["frames"]
    if gate_enabled:
        klass = GateAcquisition
    elif continuous_trigger:
        klass = ContinuousTriggerAcquisition
    elif trigger_enabled:
        klass = SingleTriggerAcquisition
    else:
        klass = InternalAcquisition
    acq = klass(signal, log, nb_frames, exp_time, nb_channels, delay_before, delay_after, nb_gates)
    acq_task = gevent.spawn(acq.run)
    acq_task.acquisition = acq
    return acq_task


class SignalOut:

    def __init__(self, address=None):
        if address is None:
            self.socket = None
        else:
            host, port = address.rsplit(":", 1)
            self.socket = gevent.socket.create_connection((host, int(port)))

    def gate_high(self):
        if self.socket:
            self.socket.sendall(b"high\n")

    def gate_low(self):
        if self.socket:
            self.socket.sendall(b"low\n")

    def __enter__(self):
        return self

    def __exit__(self, ext_type, exc_value, tb):
        if self.socket:
            self.socket.close()


class Mythen2(BaseDevice):

    protocol = Protocol

    def __init__(self, *args, **kwargs):
        trigger = kwargs.pop("trigger", {})
        self.trigger_in_address = trigger.pop("in", None)
        self.trigger_out_address = trigger.pop("out", None)
        super().__init__(*args, **kwargs)
        self.config = {name: t.default for name, t in TYPE_MAP.items()}
        self.config.update(self.props)
        if self.trigger_in_address:
            self.trigger_in_source = gevent.server.StreamServer(
                self.trigger_in_address, self.on_trigger_signal_in
            )
            self.trigger_in_source.start()
            self._log.info(
                "listenning for input trigger on TCP %s",
                self.trigger_in_address,
            )
        self.acq_task = None

    def __getitem__(self, name):
        return TYPE_MAP[name].encode(self.config)

    def __setitem__(self, name, value):
        TYPE_MAP[name].decode(self.config, value)

    def start_acquisition(self):
        signal = SignalOut(self.trigger_out_address)
        self.acq_task = start_acquisition(self.config, signal, self._log)
        return self.acq_task

    def on_trigger_signal_in(self, sock, addr):
        self._log.info("trigger input plugged: %r", addr)
        fobj = sock.makefile("rwb")
        while True:
            line = fobj.readline()
            if not line:
                self._log.info("trigger input unplugged %r", addr)
                return
            signal = line.strip().lower().decode()
            if self.acq is None:
                self._log.warning("%r ignored", signal)
                continue
            else:
                if signal == "trigger":
                    handler = self.acq.trigger
                elif signal == "high":
                    handler = self.acq.gate_high
                elif signal == "low":
                    handler = self.acq.gate_low
                else:
                    self._log.warn("unknown %r from %r", signal, addr)
                    continue
            try:
                handler()
            except Exception as error:
                self._log.error(
                    "error handling trigger input %r: %r", signal, error
                )

    @property
    def acq(self):
        if self.acq_task:
            return self.acq_task.acquisition

    def status(self):
        running = 0 if self.acq_task.ready() else 1
        exposing = (1 << 3 if self.acq.exposing else 0) if running else 0
        readout = 1 << 16 if self.acq.buffer.empty() else 0
        return struct.pack("<i", running | exposing | readout)

    def handle_message(self, message):
        self._log.info("handling: %r", message)
        for reply in self._handle_message(message):
            if reply is None:
                self._log.info("return: None")
            else:
                size = len(reply)
                if size > 40:
                    self._log.debug("return (%d) (too big, not shown)", len(reply))
                else:
                    self._log.info("return (%d): %r", len(reply), reply)
            yield reply

    def _handle_message(self, message):
        message = message.strip().decode()
        assert message[0] == "-"
        cmd, *data = message.split(" ", 1)
        cmd = cmd[1:]
        self.config["commandid"] += 1
        if cmd != "get":
            self.config["commandsetid"] += 1
        if cmd == "get":
            assert len(data) == 1
            data = data[0]
            if data == "status":
                yield self.status()
            else:
                yield self[data]
        elif cmd == "reset":
            gevent.sleep(2 + 0.5 * self.config["nmodules"])
            yield OK
        elif cmd == "start":
            self.start_acquisition()
            yield OK
        elif cmd == "stop":
            self.acq_task.kill()
            yield OK
        elif cmd == "readout":
            nb_frames = int(data[0]) if data else 1
            for _ in range(nb_frames):
                frame = self.acq.buffer.get()
                if frame is None:
                    break
                yield frame
        elif cmd in {"tau", "kthresh"}:
            self.config[cmd] = self.config["nmodules"] * [float(data[0])]
            yield OK
        else:
            assert len(data) == 1
            self[cmd] = data[0]
            yield OK
