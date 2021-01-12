import select
import concurrent.futures

import numpy as np


class ChainGroup:
    """
    Group of Mythen DCS chained together.
    * Assumes each mythen DCS in the chain connects it's output signal to the
      input signal of the next mythen DCS.
    * The first mythen is called the "master".
    * All slaves are automatically configured in gate mode
    * Trigger/gate configuration only takes effect on the master
    * Set of acquisition parameters (frames, time) are broadcasted to all mythens
    * Read acquisition parameters are taken from the master
    """

    MASTER_SET = {
        "triggermode", "continuoustrigger", "gatemode",
        "delay_trigger", "delay_frame", "num_gates"
    }

    JOIN_GET = {
        "assembly_date", "max_num_modules",
        "max_frame_rate", "firmware_version", "system_serial_number",
        "temperature",
    }

    CONCAT_GET = {
        "num_module_channels", "energy", "threshold", "badchn",
        "module_high_voltages", "module_temperatures", "module_humidities",
        "module_serial_numbers", "module_firmware_versions",
        "module_sensor_materials", "module_sensor_thicknesses", "module_sensor_widths"
    }

    def __init__(self, master, *slaves, executor=None):
        mythens = (master,) + slaves
        members = dict(
            mythen_type=type(master),
            mythen_master=master,
            mythen_slaves=slaves,
            mythens=mythens
        )
        if executor is None:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(mythens))
        members["_exec"] = executor
        self.__dict__.update(members)
        self._map(setattr, ("gatemode", True), mythens=slaves)

    def __dir__(self):
        return sorted(set(dir(type(self)) + dir(self.mythen_master)))

    def __getitem__(self, index):
        return self.mythens[index]

    def __getattr__(self, name):
        if name in self.JOIN_GET:
            return self._map(getattr, (name,))
        elif name in self.CONCAT_GET:
            results = self._map(getattr, (name,))
            if isinstance(results[0], str):
                return [item for items in results for item in items]
            return np.concatenate(results)
        else:
            return getattr(self.mythen_master, name)

    def __setattr__(self, name, value):
        if name in self.MASTER_SET:
            setattr(self.mythen_master, name, value)
        else:
            self._map(setattr, (name, value))

    def _map(self, func, args=(), kwargs=None, mythens=None):
        if mythens is None:
            mythens = self.mythens
        if kwargs is None:
            kwargs = {}
        futures = [
            self._exec.submit(func, mythen, *args, **kwargs)
            for mythen in mythens
        ]
        return [future.result() for future in futures]

    def start(self):
        slaves = reversed(self.mythen_slaves)
        self._map(self.mythen_type.start, mythens=slaves)
        self.mythen_master.start()

    def stop(self):
        return self._map(self.mythen_type.stop)

    def reset(self):
        return self._map(self.mythen_type.reset)

    @property
    def num_channels(self):
        return self.num_module_channels.sum()

    @property
    def flatfieldconf(self):
        return np.concatenate(self._map(getattr, ("flatfieldconf",)))

    @flatfieldconf.setter
    def flatfieldconf(self, value):
        offset = 0
        for mythen in self.mythens:
            end = offset + mythen.num_channels
            mythen.flatfieldconf = value[offset:end]
            offset = end

    def ireadout(self, n=None, buff=None):
        frame_channels = self.num_channels
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

        connections = {}
        offset = 0
        for mythen in self.mythens:
            num_channels = mythen.num_channels
            connections[mythen.connection] = mythen, offset, num_channels
            offset += num_channels

        write = type(self.mythen_master.connection).write
        cmd = '-readout {}'.format(n).encode()
        results = [
            self._exec.submit(write, connection, cmd)
            for connection in connections
        ]
        concurrent.futures.wait(results)
        for i in range(n):
            frame_offset = i * frame_channels
            frame  = flat[frame_offset:frame_offset + frame_channels]
            conns = set(connections)
            while conns:
                ready, _, _ = select.select(conns, (), ())
                for conn in ready:
                    mythen, offset, num_channels = connections[conn]
                    frame_view = frame[offset:offset + num_channels]
                    conn.read_exactly_into(frame_view)
                    conns.remove(conn)
            yield frame
