import socket

OK = 4*b"\x00"


def cmd(cmd, sock, dev):
    n, nset = dev.config["commandid"], dev.config["commandsetid"]
    sock.sendall(cmd)
    assert sock.recv(1024) == OK
    assert dev.config["commandid"] == n + 1
    assert dev.config["commandsetid"] == nset + 1


def query(query, sock, dev):
    n, nset = dev.config["commandid"], dev.config["commandsetid"]
    sock.sendall(query)
    result = sock.recv(1024)
    assert dev.config["commandid"] == n + 1
    assert dev.config["commandsetid"] == nset
    return result


def test_creation(server):
    smyth = server.mythen
    assert smyth is not None
    assert smyth.tcp_addr[0] == "127.0.0.1"
    assert smyth.tcp_addr[1] > 0


def test_connection(server):
    with socket.create_connection(server.mythen.tcp_addr) as sock:
        assert sock.getpeername() == server.mythen.tcp_addr


def test_version(server):
    config = server.mythen.config
    with socket.create_connection(server.mythen.tcp_addr) as sock:
        result = query(b"-get version", sock, server.mythen)


def test_acquisition(server):
    config = server.mythen.config
    with socket.create_connection(server.mythen.tcp_addr) as sock:
        sock.sendall(b"-frames 1")
        assert sock.recv(1024) == OK
        assert config["frames"] == 1
        assert config["commandid"] == 1
        assert config["commandsetid"] == 1
        sock.sendall(b"-time 1000000")  # 0.1s
        assert sock.recv(1024) == OK
        assert config["frames"] == 1
        assert config["time"] == 1_000_000
        assert config["commandid"] == 2
        assert config["commandsetid"] == 2
        sock.sendall(b"-start")
        assert sock.recv(1024) == OK
