import asyncio
import contextlib
import socket
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.backends.device import BLEDevice

from custom_components.ef_ble.eflib import connection as connection_module
from custom_components.ef_ble.eflib.connection import Connection, ConnectionState
from custom_components.ef_ble.eflib.exceptions import AuthErrors, FailedToAuthenticate
from custom_components.ef_ble.eflib.packet import Packet
from custom_components.ef_ble.eflib.pb import iot_comm_pb2

type TransportClient = Callable[..., tuple[Mock, socket.socket]]


@pytest.fixture
def connection() -> Connection:
    return Connection(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Test device", {}),
        "TEST_SERIAL",
        "TEST_USER",
        AsyncMock(),
        AsyncMock(),
    )


@pytest.fixture
def transport_client() -> Iterator[TransportClient]:
    sockets: list[socket.socket] = []

    def create(*, connected: bool = False) -> tuple[Mock, socket.socket]:
        transport, peer = socket.socketpair()
        sockets.extend((transport, peer))
        client = Mock(is_connected=connected)

        async def disconnect() -> None:
            client.is_connected = False
            transport.close()

        client.disconnect = AsyncMock(side_effect=disconnect)
        return client, transport

    yield create
    for sock in sockets:
        sock.close()


@pytest.mark.parametrize("retry", [False, True])
async def test_remote_drop_closes_transport(
    connection: Connection, transport_client: TransportClient, retry: bool
) -> None:
    client, transport = transport_client()
    connection._client = client
    connection._set_state(ConnectionState.AUTHENTICATED)
    connection._retry_on_disconnect = retry

    try:
        connection.disconnected(client)
        await connection._disconnect_client()

        client.disconnect.assert_awaited_once()
        assert transport.fileno() == -1
        assert connection._client is None
        assert (connection._reconnect_task is not None) == retry
    finally:
        await connection.disconnect()


@pytest.mark.parametrize("connected", [False, True])
async def test_explicit_disconnect_closes_transport(
    connection: Connection, transport_client: TransportClient, connected: bool
) -> None:
    client, transport = transport_client(connected=connected)
    connection._client = client

    await connection.disconnect()

    client.disconnect.assert_awaited_once()
    assert transport.fileno() == -1
    assert connection._client is None
    assert connection._state == ConnectionState.DISCONNECTED


async def test_connect_waits_for_old_transport_cleanup(
    connection: Connection,
    transport_client: TransportClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_client, old_transport = transport_client()
    new_client, new_transport = transport_client(connected=True)
    connection._client = old_client

    async def establish(*args: Any, **kwargs: Any) -> Mock:
        assert old_transport.fileno() == -1
        return new_client

    monkeypatch.setattr(connection_module, "establish_connection", establish)
    monkeypatch.setattr(
        connection_module, "close_stale_connections_by_address", AsyncMock()
    )
    monkeypatch.setattr(connection, "_validate_characteristics", Mock())
    monkeypatch.setattr(connection, "_start_notify", AsyncMock())
    monkeypatch.setattr(connection, "_reset_assemblers", Mock())
    monkeypatch.setattr(connection, "_run_auth", AsyncMock())

    try:
        await connection.connect()
        assert connection._client is new_client
        assert new_transport.fileno() != -1
        old_client.disconnect.assert_awaited_once()
    finally:
        await connection.disconnect()


async def test_late_callback_leaves_new_client_untouched(
    connection: Connection, transport_client: TransportClient
) -> None:
    old_client, _ = transport_client()
    new_client, transport = transport_client(connected=True)
    connection._client = new_client
    connection._set_state(ConnectionState.AUTHENTICATED)
    inbox = connection._inbox = asyncio.Queue()

    try:
        connection.disconnected(old_client)

        assert connection._client is new_client
        assert connection._state == ConnectionState.AUTHENTICATED
        assert connection._inbox is inbox
        assert transport.fileno() != -1
        new_client.disconnect.assert_not_awaited()
    finally:
        await connection.disconnect()


async def test_retry_connector_keeps_ownership_during_establishment(
    connection: Connection, transport_client: TransportClient
) -> None:
    client, _ = transport_client()
    connection._set_state(ConnectionState.ESTABLISHING_CONNECTION)

    connection.disconnected(client)
    await asyncio.sleep(0)

    assert connection._state == ConnectionState.ESTABLISHING_CONNECTION
    client.disconnect.assert_not_awaited()


async def test_cleanup_survives_cancelled_waiter(
    connection: Connection, transport_client: TransportClient
) -> None:
    client, transport = transport_client()
    connection._client = client
    started = asyncio.Event()
    release = asyncio.Event()

    async def disconnect() -> None:
        started.set()
        await release.wait()
        transport.close()

    client.disconnect.side_effect = disconnect
    waiter = asyncio.create_task(connection._disconnect_client())
    try:
        await asyncio.wait_for(started.wait(), 1)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        release.set()
        await connection.disconnect()
        assert transport.fileno() == -1
        client.disconnect.assert_awaited_once()
    finally:
        release.set()
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter


async def test_unload_waits_for_callback_cleanup(
    connection: Connection, transport_client: TransportClient
) -> None:
    client, transport = transport_client()
    connection._client = client
    connection._set_state(ConnectionState.AUTHENTICATED)
    started = asyncio.Event()
    release = asyncio.Event()

    async def disconnect() -> None:
        started.set()
        await release.wait()
        transport.close()

    client.disconnect.side_effect = disconnect
    unload = None
    try:
        connection.disconnected(client)
        await asyncio.wait_for(started.wait(), 1)
        unload = asyncio.create_task(connection.disconnect())
        await asyncio.sleep(0)
        assert not unload.done()
        release.set()
        await unload
        assert transport.fileno() == -1
        client.disconnect.assert_awaited_once()
    finally:
        release.set()
        if unload is not None:
            await unload


async def test_auth_cancellation_does_not_interrupt_cleanup(
    connection: Connection, transport_client: TransportClient
) -> None:
    client, transport = transport_client(connected=True)
    connection._client = client
    connection._set_state(ConnectionState.AUTHENTICATED)

    async def disconnect() -> None:
        client.is_connected = False
        connection.disconnected(client)
        await asyncio.sleep(0)
        transport.close()

    client.disconnect.side_effect = disconnect
    auth = connection._auth_task = asyncio.create_task(connection._disconnect_client())
    with pytest.raises(asyncio.CancelledError):
        await auth
    await connection.disconnect()

    assert transport.fileno() == -1
    client.disconnect.assert_awaited_once()


async def test_disconnect_timeout_remains_bounded(
    connection: Connection,
    transport_client: TransportClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = transport_client()
    connection._client = client
    client.disconnect.side_effect = asyncio.Event().wait
    monkeypatch.setattr(connection_module, "DISCONNECT_TIMEOUT", 0.01)

    await asyncio.wait_for(connection.disconnect(), 1)

    assert connection._client is None
    assert connection.disconnect_log[-1]["outcome"] == "timeout"


async def test_disconnect_log_keeps_calling_context(
    connection: Connection, transport_client: TransportClient
) -> None:
    client, _ = transport_client(connected=True)
    connection._client = client

    async def request_cleanup() -> None:
        await connection._disconnect_client()

    await request_cleanup()

    assert "request_cleanup" in connection.disconnect_log[-1]["trigger"]


async def test_status_packet_before_auth_reply_does_not_confirm_auth(
    connection: Connection,
):
    connection._client = Mock()
    connection._disconnect_client = AsyncMock()
    connection._data_parse = AsyncMock(return_value=True)
    connection._set_state(ConnectionState.AUTHENTICATING)

    status = Packet(0x35, 0x21, 0x35, 0x89, bytes.fromhex("0100"), 0x01, 0x01, 0x03)
    rejected = Packet(0x35, 0x21, 0x35, 0x86, bytes.fromhex("06"), 0x01, 0x01, 0x03)

    await connection._process_packets([status])
    assert connection._state == ConnectionState.AUTHENTICATING

    with pytest.raises(AuthErrors.WrongKey):
        await connection._process_packets([rejected])
    assert connection._state == ConnectionState.ERROR_AUTH_FAILED


@pytest.mark.parametrize(
    ("auth_mode", "rejected_command"),
    [
        ("legacy", None),
        ("machine", None),
        ("certificate", None),
        ("machine", 0xA8),
        ("certificate", 0xAA),
        ("certificate", 0xAB),
    ],
)
async def test_authentication_survives_interleaved_notifications(
    monkeypatch: pytest.MonkeyPatch,
    auth_mode: str,
    rejected_command: int | None,
) -> None:
    client = Mock(is_connected=True)
    notify: Callable[[object, bytearray], Awaitable[None]]

    async def subscribe(
        characteristic: object,
        callback: Callable[[object, bytearray], Awaitable[None]],
        **kwargs: Any,
    ) -> None:
        nonlocal notify
        notify = callback

    async def write(characteristic: object, data: bytearray, **kwargs: Any) -> None:
        packet = Packet.from_bytes(bytes(data))
        assert isinstance(packet, Packet)
        result = 1 if packet.cmd_id == rejected_command else 0
        match packet.cmd_id:
            case 0x89:
                payload = b"\x01\x00"
            case 0xA8:
                payload = bytes([result]) + b"R" * 64 + b"S" * 64 + bytes(5)
            case 0xAA:
                payload = iot_comm_pb2.RefreshTokenAck(
                    result=result, user_token="TEST_TOKEN"
                ).SerializeToString()
            case 0xAB:
                authentication = iot_comm_pb2.Authentication.FromString(packet.payload)
                assert authentication.user_token == "TEST_TOKEN"
                payload = iot_comm_pb2.AuthenticationAck(
                    result=result
                ).SerializeToString()
            case 0x86:
                payload = b"\x00"
            case _:
                pytest.fail(f"Unexpected authentication command: {packet.cmd_id:#x}")

        if packet.cmd_id != 0x89:
            telemetry = Packet(0x03, 0x21, 0x03, 0x1C)
            await notify(characteristic, bytearray(telemetry.to_bytes()))
        reply = Packet(packet.dst, packet.src, packet.cmd_set, packet.cmd_id, payload)
        await notify(characteristic, bytearray(reply.to_bytes()))

    async def disconnect() -> None:
        client.is_connected = False

    client.start_notify = AsyncMock(side_effect=subscribe)
    client.write_gatt_char = AsyncMock(side_effect=write)
    client.disconnect = AsyncMock(side_effect=disconnect)
    monkeypatch.setattr(
        connection_module, "establish_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        connection_module, "close_stale_connections_by_address", AsyncMock()
    )

    async def packet_parse(data: bytes) -> Packet:
        packet = Packet.from_bytes(data)
        assert isinstance(packet, Packet)
        return packet

    bind_provider = (
        AsyncMock(
            return_value=Mock(random_code="TEST_RANDOM", user_info_en="TEST_BIND_DATA")
        )
        if auth_mode == "certificate"
        else None
    )
    conn = Connection(
        BLEDevice("AA:BB:CC:DD:EE:FF", "Test device", {}),
        "TEST_SERIAL",
        "TEST_USER",
        AsyncMock(return_value=True),
        packet_parse,
        encrypt_type=0,
        bind_data_provider=bind_provider,
        uses_machine_auth=auth_mode == "machine",
    ).with_disabled_reconnect()
    states: list[ConnectionState] = []
    conn.on_state_change(states.append)
    try:
        async with asyncio.timeout(1):
            await conn.connect()
            state, error = await conn.wait_until_authenticated_or_error(return_exc=True)

        if rejected_command is None:
            assert state == ConnectionState.AUTHENTICATED
            assert error is None
        else:
            assert state == ConnectionState.ERROR_AUTH_FAILED
            assert isinstance(error, FailedToAuthenticate)
            assert ConnectionState.AUTHENTICATED not in states
        client.start_notify.assert_awaited_once()
    finally:
        await conn.disconnect()
