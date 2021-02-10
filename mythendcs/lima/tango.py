from tango import DevState, Util
from tango.server import Device, device_property, attribute, command

from . import camera
from ..core import mythen_table


class MythenDCS(Device):

    address = device_property(dtype=[str])

    def init_device(self):
        super().init_device()
        self.ctrl = get_control(self.address)

    @property
    def mythen(self):
        return self.ctrl.hwInterface().detector

    def dev_state(self):
        status = self.mythen.status
        return DevState.RUNNING if status  == "RUNNING" else DevState.ON

    def dev_status(self):
        return self.mythen.status

    @attribute(dtype=int)
    def nb_active_modules(self):
        return self.mythen.get_active_modules()

    @nb_active_modules.setter
    def nb_active_modules(self, nb_active_modules):
        self.mythen.set_active_modules(nb_active_modules)

    @attribute(dtype=bool)
    def rate_correction(self):
        return self.mythen.rate

    @rate_correction.setter
    def rate_correction(self, enable):
        self.mythen.rate = enable

    @attribute(dtype=bool)
    def flatfield_correction(self):
        return self.mythen.flatfield

    @flatfield_correction.setter
    def flatfield_correction(self, enable):
        self.mythen.flatfield = enable

    @attribute(dtype=bool)
    def bad_channel_interpolation(self):
        return self.mythen.badchnintrpl

    @bad_channel_interpolation.setter
    def bad_channel_interpolation(self, enable):
        self.mythen.badchnintrpl = enable

    @attribute(dtype=int)
    def readout_bits(self):
        return self.mythen.readoutbits

    @readout_bits.setter
    def readout_bits(self, nbits):
        self.mythen.readoutbits = nbits

    @attribute(dtype=str)
    def version(self):
        return self.mythen.version

    @attribute(dtype=bool)
    def trigger_enabled(self):
        return self.mythen.triggermode

    @attribute(dtype=bool)
    def continuous_trigger_enabled(self):
        return self.mythen.continuoustrigger

    @attribute(dtype=bool)
    def gate_enabled(self):
        return self.mythen.gatemode

    @attribute(dtype=int)
    def nb_gates(self):
        return self.mythen.num_gates

    @attribute(dtype=[float], unit="keV", max_dim_x=24)
    def threshold(self):
        return self.mythen.threshold

    @threshold.setter
    def threshold(self, threshold):
        assert len(threshold) == 1
        self.mythen.threshold = threshold[0]

    @attribute(dtype=[float], unit="s", max_dim_x=24)
    def tau(self):
        return self.mythen.tau

    @tau.setter
    def tau(self, tau):
        assert len(tau) == 1
        self.mythen.tau = tau[0]

    @command(dtype_out=str)
    def repr(self):
        return repr(self.mythen)

    @command
    def reset(self):
        self.mythen.reset()

    @command(dtype_out=str)
    def dump(self):
        table, mod_table = mythen_table(self.mythen)
        mod_table.maxwidth = 140
        return "{}\n\n{}".format(table, mod_table)


def get_tango_specific_class_n_device():
    return MythenDCS


_MYTHEN = None
def get_control(address):
    print(address)
    global _MYTHEN
    if _MYTHEN is None:
        _MYTHEN = camera.get_control(address)
    return _MYTHEN


def main():
    import Lima.Server.LimaCCDs
    Lima.Server.LimaCCDs.main()


if __name__ == '__main__':
    main()
