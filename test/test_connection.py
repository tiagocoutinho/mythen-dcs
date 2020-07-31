import socket

import numpy
import pytest

from mythendcs.core import Connection, TCP, UDP, TCP_PORT, UDP_PORT, DEFAULT_TIMEOUT


tcp_udp = pytest.mark.parametrize(
    "conn", [TCP, UDP], ids=['tcp', 'udp'], indirect=True
)

timeout = pytest.mark.parametrize(
    "timeout", [DEFAULT_TIMEOUT, None, 0.1, 1, 1000],
    ids=['t({})'.format(i) for i in ('default', 'none', 0.1, 1, 1000)]
)

version_buffer = pytest.mark.parametrize(
    "buff", [bytearray(7*b"\xfe"), numpy.full(7, b"\xfe")],
    ids=["bytearray", "numpy"]
)


@pytest.mark.parametrize(
    "host, port, kind",
    [("127.0.0.1", 10031, TCP), ("127.0.0.1", 10031, UDP)],
    ids=["tcp", "udp"])
def test_no_connection(host, port, kind):
    conn = Connection(host, port, kind=kind)
    assert conn.socket is None
    assert conn.host == host
    assert conn.port == port
    assert conn.kind == kind
    assert "pending" in repr(conn)


@pytest.mark.parametrize(
    "url, host, port, kind",
    [("tcp://mythen.acme.org:11223", "mythen.acme.org", 11223, TCP),
     ("udp://55.33.22.11:9988", "55.33.22.11", 9988, UDP),
     ("mythen.acme.org:556", "mythen.acme.org", 556, TCP)],
    ids=["tcp", "udp", "implicit-tcp"])
def test_from_url(url, host, port, kind):
    conn = Connection.from_url(url)
    assert conn.socket is None
    assert conn.host == host
    assert conn.port == port
    assert conn.kind == kind
    assert "pending" in repr(conn)


def test_connection(server):
    host, port = server.mythen.tcp_addr
    tcp = Connection(host, port)
    assert tcp.socket is None
    assert "pending" in repr(tcp)
    assert tcp.kind == TCP

    host, port = server.mythen.udp_addr
    udp = Connection(host, port, kind=UDP)
    assert udp.socket is None
    assert "pending" in repr(udp)
    assert udp.kind == UDP


@tcp_udp
@timeout
def test_write_and_read(server, conn, timeout):
    version = server.mythen.config["version"].encode()
    conn.write(b"-get version")
    assert conn.read(1024, timeout=timeout) == version


@tcp_udp
@timeout
@version_buffer
def test_write_and_read_exactly_into(server, conn, timeout, buff):
    version = server.mythen.config["version"].encode()
    conn.write(b"-get version")
    conn.read_exactly_into(buff, timeout=timeout)
    assert bytes(buff) == version


@tcp_udp
@timeout
def test_write_read(server, conn, timeout):
    version = server.mythen.config["version"].encode()
    assert conn.write_read(b"-get version", 1024, timeout=timeout) == version


@tcp_udp
@timeout
@version_buffer
def test_write_read_exactly_into(server, conn, timeout, buff):
    version = server.mythen.config["version"].encode()
    conn.write_read_exactly_into(b"-get version", buff, timeout=timeout)
    assert bytes(buff) == version


@tcp_udp
def test_timeout(server, conn):
    with pytest.raises(socket.timeout):
        conn.write_read(b"-reset", 1024, timeout=0.1)

    version = server.mythen.config["version"].encode()
    assert conn.write_read(b"-get version", 1024, timeout=0.1) == version

    with pytest.raises(socket.timeout):
        conn.write_read(b"-reset", 1024, timeout=0.1)


@tcp_udp
def test_server_kill(server, conn):
    version = server.mythen.config["version"].encode()
    assert conn.write_read(b"-get version", 1024) == version

    server.stop_thread_safe()

    with pytest.raises(OSError):
        assert conn.write_read(b"-get version", 1024, timeout=0.1) == version
