import socket
import threading

import gevent.event
import pytest

from sinstruments.simulator import create_server_from_config
from mythendcs.core import Mythen, Connection, TCP, UDP, mythen_for_url


@pytest.fixture
def server():

    serv = None

    def run():
        nonlocal serv

        def stop():
            watcher.start(stop_event.set)
            watcher.send()
            # need to create a connection to trigger a wake up
            # event on the server so it shuts down
            try:
                with socket.create_connection(serv.mythen.tcp_addr):
                    pass
            except OSError:
                pass
            stopped_event.wait()

        serv = create_server_from_config(config)
        watcher = gevent.get_hub().loop.async_()
        stop_event = gevent.event.Event()
        serv.mythen = serv.get_device_by_name("sim-myth")
        tcp, udp = serv.devices[serv.mythen]
        tcp.start()
        udp.start()
        serv.stop_thread_safe = stop
        serv.mythen.tcp_addr = tcp.address
        serv.mythen.udp_addr = udp.address
        started_event.set()
        stop_event.wait()
        tcp.stop()
        udp.stop()
        watcher.close()
        stopped_event.set()

    config = {
        "devices": [
            {
                "name": "sim-myth",
                "class": "Mythen2",
                "package": "mythendcs.simulator",
                "nmodules": 4,
                "transports": [
                    dict(type="tcp", url="127.0.0.1:0"),
                    dict(type="udp", url="127.0.0.1:0")
                ],
                "external_signal": "127.0.0.1:0"
            }
        ]
    }

    started_event = threading.Event()
    stopped_event = threading.Event()
    thread = threading.Thread(target=run)
    thread.start()
    started_event.wait()
    serv.thread = thread
    try:
        yield serv
    finally:
        serv.stop_thread_safe()
        thread.join()


@pytest.fixture
def tcp_conn(server):
    host, port = server.mythen.tcp_addr
    yield Connection(host, port)


@pytest.fixture
def udp_conn(server):
    host, port = server.mythen.udp_addr
    yield Connection(host, port, kind=UDP)


def _conn(server, kind):
    if kind == TCP:
        host, port = server.mythen.tcp_addr
    elif kind == UDP:
        host, port = server.mythen.udp_addr
    else:
        raise ValueError('unsupported socket kind %r' % kind)
    return Connection(host, port, kind=kind)
    conn.server = server
    return conn


@pytest.fixture
def conn(server, request):
    conn = _conn(server, request.param)
    conn.server = server
    yield conn


@pytest.fixture
def mythen(server, request):
    kind = request.param
    if kind == TCP:
        scheme, (host, port) = 'tcp', server.mythen.tcp_addr
    elif kind == UDP:
        scheme, (host, port) = 'udp', server.mythen.udp_addr
    else:
        raise ValueError('unsupported socket kind %r' % kind)
    url = '{}://{}:{}'.format(scheme, host, port)
    mythen = mythen_for_url(url)
    mythen.server = server
    yield mythen
