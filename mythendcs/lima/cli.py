import struct
import asyncio
import contextlib
import urllib.parse

import click
import Lima.Core
from beautifultable import BeautifulTable
from limatb.cli import camera, url, table_style, max_width
from limatb.info import info_list
from limatb.network import get_subnet_addresses, get_host_by_addr

from .camera import Interface
from ..core import TCP, UDP, TCP_PORT, UDP_PORT, Mythen, Channel


@camera(name="mythendcs")
@url
@click.pass_context
def mythendcs(ctx, url):
    """Dectris Mythen 2 specific commands"""
    if url is None:
        return
    if "://" not in url:
        url = ("udp://" if str(UDP_PORT) in url else "tcp://") + url
    url = urllib.parse.urlparse(url)
    scheme, port = url.scheme, url.port
    if port is None:
        port = UDP_PORT if scheme == "udp" else TCP_PORT
    kind = UDP if scheme == "udp" else TCP
    channel = Channel(url.hostname, port, kind=kind)
    camera = Mythen(channel)
    interface = Interface(camera)
    interface.camera = camera
    ctx.obj['camera'] = camera
    return interface


async def test_communication(address, port):
    reader, writer = await asyncio.open_connection(address, port)
    with contextlib.closing(writer):
        writer.write(b"-get version")
        await writer.drain()
        data = (await reader.readexactly(7)).decode().strip()
        host = (await get_host_by_addr(address)).name
        return dict(version=data, host=host, address=address, port=port)


async def find_detectors(port=TCP_PORT, timeout=2.0):
    detectors = []
    addresses = get_subnet_addresses()
    coros = [test_communication(address, port) for address in addresses]
    try:
        for task in asyncio.as_completed(coros, timeout=timeout):
            try:
                detector = await task
            except OSError as error:
                continue
            if detector is not None:
                detectors.append(detector)
    except asyncio.TimeoutError:
        pass
    return detectors


def detector_table(detectors):
    import beautifultable

    width = click.get_terminal_size()[0]
    table = beautifultable.BeautifulTable(max_width=width)

    table.column_headers = ["Host", "IP", "Port", "Version"]
    for detector in detectors:
        table.append_row(
            (detector["host"], detector["address"],
             detector["port"], detector["version"])
        )
    return table


async def scan(port=TCP_PORT, timeout=2.0):
    detectors = await find_detectors(port, timeout)
    return detector_table(detectors)


@mythendcs.command("scan")
@click.option('-p', '--port', default=TCP_PORT)
@click.option('--timeout', default=2.0)
@table_style
@max_width
def mythen_scan(port, timeout, table_style, max_width):
    """show accessible sls detectors on the network"""
    table = asyncio.run(scan(port, timeout))
    style = getattr(table, "STYLE_" + table_style.upper())
    table.set_style(style)
    table.max_table_width = max_width
    click.echo(table)
