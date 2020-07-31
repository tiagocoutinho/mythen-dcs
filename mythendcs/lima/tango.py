from tango import DevState, Util
from tango.server import Device, device_property, attribute

from .camera import get_control


class MythenDCS(Device):

    address = device_property(dtype=str)

    def init_device(self):
        super().init_device()
        self.ctrl = get_control()

    @property
    def mythen(self):
        return self.ctrl.hwInterface().detector

    def dev_state(self):
        status = self.mythen.run_status
        if status in (RunStatus.WAITING, RunStatus.TRANSMITTING,
                      RunStatus.RUNNING):
            return DevState.RUNNING
        elif status == RunStatus.ERROR:
            return DevState.FAULT
        return DevState.ON

    @attribute(dtype=[int], unit="keV", max_dim_x=24)
    def threshold(self):
        return self.mythen.threshold

    @energy_threshold.setter
    def threshold(self, threshold):
        assert len(threshold) == 1
        self.mythen.threshold = threshold[0]


def get_tango_specific_class_n_device():
    return MythenDCS


_MYTHENS = {}
def get_control(address=None):
    mythen = _MYTHENS.get(address)
    if mythen is None:
        if address is None:
            # if there is no address use TCP and the server instance
            # name as host
            host = Util.instance().get_ds_inst_name()
            address = "tcp://{}:1031".format(host)
        _MYTHENS[address] = mythen = get_control(address)
    return mythen


def main():
    import Lima.Server.LimaCCDs
    Lima.Server.LimaCCDs.main()


if __name__ == '__main__':
    main()
