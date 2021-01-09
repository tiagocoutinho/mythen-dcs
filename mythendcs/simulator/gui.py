import time
import itertools
import functools
import pkg_resources

import typer
import pyqtgraph
from PyQt5 import Qt, uic
from sinstruments.simulator import parse_config_file


_pens = itertools.cycle([pyqtgraph.mkPen(c) for c in "rgbcmykw"])
pen = lambda: next(_pens)

UI_FILENAME = pkg_resources.resource_filename('mythendcs.simulator', 'gui.ui')


def send_signal(sock, port, high):
    signal = "high" if high else "low"
    sock.writeDatagram(f"{signal} {time.time()}\n".encode(), Qt.QHostAddress.Broadcast, port)


def send_trigger(sock, port):
    send_signal(sock, port, 1)
    send_signal(sock, port, 0)


def udp(port, open_mode=Qt.QUdpSocket.ReadWrite):
    bind_mode = Qt.QUdpSocket.ShareAddress | Qt.QUdpSocket.ReuseAddressHint
    sock = Qt.QUdpSocket()
    if not sock.bind(Qt.QHostAddress.Broadcast, port, bind_mode):
        raise ValueError(f"could not bind to port {port}")
    sock.open(open_mode)
    return sock


def on_data(sock, curve, high=1, low=0):
    message = sock.receiveDatagram(64)
    if not message.isValid():
        return
    x, y = curve._curve_data
    data = bytes(message.data())
    signal, *ts = data.split(b" ")
    v = high if signal == b'high' else low
    ts = float(ts[0]) if ts else time.time()
    if not y:
        x.append(ts - 1)
        y.append(low)
    x.append(ts)
    y.append(y[-1])
    x.append(ts)
    y.append(v)
    curve.setData(x, y)


def main(config: str = typer.Option(..., "-c", "--config-file", callback=parse_config_file)):

    app = Qt.QApplication([])
    wnd = Qt.QMainWindow()
    uic.loadUi(UI_FILENAME, baseinstance=wnd)
    wnd.plot.setTitle("Mythen simulator output signal sniffer")
    wnd.plot.setLabels(bottom="time")
    wnd.plot.setAxisItems({"bottom": pyqtgraph.DateAxisItem()})
    wnd.plot.showGrid(x=True, y=True)
    wnd.plot.addLegend()

    def clear_plot():
        for detector in detectors.values():
            curve = detector["out_curve"]
            curve._curve_data = [], []
            curve.setData(*curve._curve_data)


    wnd.action_clear.triggered.connect(clear_plot)

    detectors = {}
    for i, device in enumerate(config["devices"]):
            #if i>0:continue
        if device["class"] != "Mythen2" or device["package"] != "mythendcs.simulator":
            continue
        sig = device.get("signal", {})
        sin, sout = sig.get('in'), sig.get('out')
        name = device["name"]
        detectors[name] = detector = {}
        if sin is not None:
            dock = Qt.QDockWidget(name)
            wnd.addDockWidget(Qt.Qt.LeftDockWidgetArea, dock)
            det_panel = Qt.QWidget()
            dock.setWidget(det_panel)
            layout = Qt.QHBoxLayout(det_panel)
            port = int(sin.rsplit(":", 1)[-1])
            sock = udp(port)
            gate_btn = Qt.QPushButton("Gate")
            gate_btn.setCheckable(True)
            gate_btn.toggled.connect(functools.partial(send_signal, sock, port))
            trig_btn = Qt.QPushButton("Trigger")
            trig_btn.clicked.connect(functools.partial(send_trigger, sock, port))
            layout.addWidget(trig_btn)
            layout.addWidget(gate_btn)
            detector["in"] = sock
        if sout is not None:
            print(f"sniffing for signals coming from {name}@{sout}")
            sock = udp(sout, open_mode=Qt.QUdpSocket.ReadOnly)
            curve_data = [], []
            curve = wnd.plot.plot(*curve_data, pen=pen(), name=name)
            curve._curve_data = curve_data
            base = 1.1 * i
            slot = functools.partial(on_data, sock, curve, high=1 + base, low=base)
            sock.readyRead.connect(slot)
            detector["out"] = sock
            detector["out_curve"] = curve
            #plot.addItem(curve)

    wnd.show()
    app.exec_()


if __name__ == "__main__":
    typer.run(main)
