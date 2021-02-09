import socket
import threading

import gevent.event
import pytest

from sinstruments.pytest import server_context
from sinstruments.simulator import create_server_from_config
from mythendcs.core import Mythen, Connection, TCP, UDP, mythen_for_url


@pytest.fixture()
def config():
    return {
        "devices": [
            {
                "name": "sim-myth",
                "class": "MythenDCS",
                "nmodules": 4,
                "transports": [
                    dict(type="tcp", url="127.0.0.1:0"),
                    dict(type="udp", url="127.0.0.1:0")
                ],
                "external_signal": "127.0.0.1:0"
            }
        ]
    }


@pytest.fixture
def server(config):
    with server_context(config) as serv:
        serv.mythen = serv.devices["sim-myth"]
        tcp, udp = serv.mythen.transports
        serv.mythen.tcp_addr = tcp.address
        serv.mythen.udp_addr = udp.address
        yield serv


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
