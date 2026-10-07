import asyncio
import json

from solders.rpc.responses import LogsNotification, parse_websocket_message

from bot.pool_monitor import PoolMonitor, redact_url

SIGNATURE = "5" * 88


def logs_notification(subscription: int, logs, err=None) -> LogsNotification:
    # Parsed the same way solana-py's recv() does
    [message] = parse_websocket_message(json.dumps({
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "subscription": subscription,
            "result": {
                "context": {"slot": 1},
                "value": {"signature": SIGNATURE, "err": err, "logs": logs},
            },
        },
    }))
    return message


def make_monitor():
    monitor = PoolMonitor(ws_url="wss://example.com", rpc_url="https://example.com")
    detected = []
    monitor.add_pool_callback(detected.append)
    return monitor, detected


def subscribe(monitor, request_id: int, dex: str, subscription: int) -> None:
    monitor._pending_requests[request_id] = dex
    [result] = parse_websocket_message(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": subscription}))
    asyncio.run(monitor._process_message(result))


def test_subscription_result_maps_server_id_to_dex():
    monitor, _ = make_monitor()
    subscribe(monitor, 1, "pumpfun", 42)
    assert monitor._subscriptions == {42: "pumpfun"}
    assert monitor._pending_requests == {}


def test_pool_creation_detected_for_matching_dex():
    monitor, detected = make_monitor()
    subscribe(monitor, 1, "pumpfun", 42)
    asyncio.run(monitor._process_message(logs_notification(42, ["Program log: Instruction: Create"])))
    assert len(detected) == 1
    assert detected[0].dex == "pumpfun"
    assert detected[0].signature == SIGNATURE
    assert monitor.pools_detected == 1


def test_unrelated_and_failed_transactions_are_ignored():
    monitor, detected = make_monitor()
    subscribe(monitor, 1, "raydium", 7)
    asyncio.run(monitor._process_message(logs_notification(7, ["Program log: Instruction: Swap"])))
    asyncio.run(monitor._process_message(
        logs_notification(7, ["Program log: initialize2: InitializeInstruction2"], err={"InstructionError": [0, "InvalidAccountData"]})
    ))
    asyncio.run(monitor._process_message(logs_notification(99, ["Program log: initialize2"])))
    assert detected == []


def test_redact_url_hides_api_key():
    assert redact_url("https://mainnet.helius-rpc.com/?api-key=secret") == "https://mainnet.helius-rpc.com"
    assert "secret" not in redact_url("wss://host.quiknode.pro/secret/")


def test_only_transient_errors_are_retried():
    from websockets.datastructures import Headers
    from websockets.exceptions import ConnectionClosedError, InvalidStatus
    from websockets.http11 import Response

    from bot.pool_monitor import _is_transient

    def status(code):
        return InvalidStatus(Response(code, "", Headers()))

    assert _is_transient(ConnectionClosedError(None, None))
    assert _is_transient(ConnectionRefusedError())
    assert _is_transient(status(429))
    assert _is_transient(status(503))
    assert not _is_transient(status(401))
    assert not _is_transient(ValueError("bad response"))
