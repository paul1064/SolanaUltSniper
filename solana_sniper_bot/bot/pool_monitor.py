"""
Pool Monitor for the Solana Sniper Bot.

Monitors DEXes (Raydium, Orca, Pump.fun) for new liquidity pools
using WebSocket subscriptions for real-time detection.
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from urllib.parse import urlsplit

from solana.rpc.websocket_api import connect
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.rpc.responses import LogsNotification, SubscriptionResult
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger(__name__)

# Known DEX program IDs on mainnet
RAYDIUM_AMM_V4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
ORCA_WHIRLPOOL = Pubkey.from_string("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc")
PUMPFUN_MAIN = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")

# Log lines emitted by each program when a new pool / token is created
POOL_CREATION_MARKERS = {
    "raydium": ("initialize2",),
    "orca": ("Instruction: InitializePool",),
    "pumpfun": ("Instruction: Create",),
}


def _is_transient(error: Exception) -> bool:
    """Network drops, rate limits and server errors are retried; config errors (401/403) are not."""
    if isinstance(error, InvalidStatus):
        status = error.response.status_code
        return status == 429 or status >= 500
    return isinstance(error, (ConnectionClosed, OSError, asyncio.TimeoutError))


def redact_url(url: str) -> str:
    """Strip path and query (which often carry API keys) from an RPC URL for logging."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname or ''}"


@dataclass
class PoolInfo:
    """Information about a liquidity pool."""
    
    pool_address: str
    token_address: str
    base_mint: str  # Usually SOL
    quote_mint: str  # The new token
    liquidity_sol: float
    liquidity_tokens: float
    creation_timestamp: float
    
    # DEX information
    dex: str  # 'raydium', 'orca', 'pumpfun'
    program_id: str
    
    # Token metadata (if available)
    token_metadata: Dict[str, Any] = None
    
    # Additional data
    signature: str = ""
    creator_address: Optional[str] = None
    initial_liquidity_sol: Optional[float] = None
    
    def __post_init__(self):
        if self.token_metadata is None:
            self.token_metadata = {}


class PoolMonitor:
    """
    Real-time monitor for new liquidity pools.
    
    Monitors multiple DEXes simultaneously:
    - Raydium AMM V4
    - Orca Whirlpool
    - Pump.fun
    
    Uses WebSocket log subscriptions for instant detection and
    reconnects automatically when the connection drops.
    """
    
    RECONNECT_BASE_DELAY = 1.0
    RECONNECT_MAX_DELAY = 30.0
    
    def __init__(
        self,
        ws_url: str,
        rpc_url: str,
        monitor_raydium: bool = True,
        monitor_orca: bool = True,
        monitor_pumpfun: bool = True,
    ):
        """
        Initialize pool monitor.
        
        Args:
            ws_url: WebSocket RPC URL
            rpc_url: HTTP RPC URL
            monitor_raydium: Enable Raydium monitoring
            monitor_orca: Enable Orca monitoring
            monitor_pumpfun: Enable Pump.fun monitoring
        """
        self.ws_url = ws_url
        self.rpc_url = rpc_url
        
        self._programs: Dict[str, Pubkey] = {}
        if monitor_raydium:
            self._programs["raydium"] = RAYDIUM_AMM_V4
        if monitor_orca:
            self._programs["orca"] = ORCA_WHIRLPOOL
        if monitor_pumpfun:
            self._programs["pumpfun"] = PUMPFUN_MAIN
        
        # Callbacks for new pools
        self._pool_callbacks: List[Callable] = []
        
        # Connection state
        self._ws_connection = None
        self._pending_requests: Dict[int, str] = {}  # request id -> dex
        self._subscriptions: Dict[int, str] = {}  # server subscription id -> dex
        self._running = False
        
        # Statistics
        self.pools_detected = 0
        self.last_pool_time = 0.0
        
        logger.info("PoolMonitor initialized")
    
    def add_pool_callback(self, callback: Callable[[PoolInfo], None]) -> None:
        """
        Add a callback to be called when a new pool is detected.
        
        Args:
            callback: Async function that takes PoolInfo as argument
        """
        self._pool_callbacks.append(callback)
        logger.info(f"Added pool callback. Total callbacks: {len(self._pool_callbacks)}")
    
    async def start(self) -> None:
        """Start monitoring for new pools. Runs until stop() is called."""
        if self._running:
            logger.warning("PoolMonitor already running")
            return
        if not self._programs:
            raise ValueError("No DEX enabled - enable at least one of MONITOR_RAYDIUM/ORCA/PUMPFUN")
        
        self._running = True
        logger.info("Starting PoolMonitor...")
        
        delay = self.RECONNECT_BASE_DELAY
        try:
            while self._running:
                try:
                    logger.info(f"Connecting to WebSocket: {redact_url(self.ws_url)}")
                    async with connect(self.ws_url) as ws:
                        self._ws_connection = ws
                        await self._subscribe_all()
                        delay = self.RECONNECT_BASE_DELAY
                        await self._listen_for_events()
                except Exception as e:
                    if not self._running:
                        break
                    if not _is_transient(e):
                        raise
                    logger.warning(f"WebSocket connection lost ({e}); reconnecting in {delay:.0f}s")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.RECONNECT_MAX_DELAY)
                finally:
                    self._ws_connection = None
                    self._pending_requests.clear()
                    self._subscriptions.clear()
        finally:
            self._running = False
    
    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        
        if self._ws_connection:
            await self._ws_connection.close()
        
        logger.info("PoolMonitor stopped")
    
    async def _subscribe_all(self) -> None:
        """Subscribe to the logs of every enabled DEX program."""
        for dex_name, program_id in self._programs.items():
            logger.info(f"Subscribing to {dex_name} program: {program_id}")
            request_id = await self._ws_connection.logs_subscribe(
                RpcTransactionLogsFilterMentions(program_id),
                commitment="confirmed",
            )
            self._pending_requests[request_id] = dex_name
    
    async def _listen_for_events(self) -> None:
        """Listen for log events until the connection closes or the monitor stops."""
        logger.info("Listening for pool creation events...")
        
        while self._running:
            # recv() raises ConnectionClosed when the socket dies, which start() turns into a reconnect
            messages = await self._ws_connection.recv()
            for message in messages:
                try:
                    await self._process_message(message)
                except Exception:
                    logger.exception("Error processing WebSocket message")
    
    async def _process_message(self, message: Any) -> None:
        """
        Process a parsed WebSocket message.
        
        Args:
            message: SubscriptionResult or LogsNotification from solana-py
        """
        if isinstance(message, SubscriptionResult):
            dex_name = self._pending_requests.pop(message.id, None)
            if dex_name is not None:
                self._subscriptions[message.result] = dex_name
                logger.info(f"Subscribed to {dex_name} (subscription ID: {message.result})")
            return
        
        if not isinstance(message, LogsNotification):
            return
        
        dex_name = self._subscriptions.get(message.subscription)
        value = message.result.value
        if dex_name is None or value.err is not None:
            # Unknown subscription or failed transaction
            return
        
        pool_info = self._parse_pool_creation(dex_name, value.logs, str(value.signature))
        if pool_info is None:
            return
        
        self.pools_detected += 1
        self.last_pool_time = time.time()
        
        logger.info(
            f"🆕 New pool detected on {pool_info.dex}! | TX: {pool_info.signature[:16]}..."
        )
        
        await self._notify_callbacks(pool_info)
    
    def _parse_pool_creation(
        self,
        dex_name: str,
        logs: List[str],
        signature: str,
    ) -> Optional[PoolInfo]:
        """
        Parse logs to detect pool creation.
        
        Detection only looks at the program's log markers. Pool/token addresses
        and reserves are not part of the logs; in production, fetch the
        transaction (getTransaction) and read them from its accounts.
        
        Args:
            dex_name: DEX the subscription belongs to
            logs: Transaction log messages
            signature: Transaction signature
            
        Returns:
            PoolInfo if pool creation detected, None otherwise
        """
        markers = POOL_CREATION_MARKERS[dex_name]
        if not any(marker in log for log in logs for marker in markers):
            return None
        
        return PoolInfo(
            pool_address="",  # Unresolved - requires getTransaction
            token_address="",  # Unresolved - requires getTransaction
            base_mint="So11111111111111111111111111111111111111112",  # Wrapped SOL
            quote_mint="",
            liquidity_sol=0.0,  # Unknown until reserves are fetched
            liquidity_tokens=0.0,
            creation_timestamp=time.time(),
            dex=dex_name,
            program_id=str(self._programs[dex_name]),
            signature=signature,
        )
    
    async def _notify_callbacks(self, pool_info: PoolInfo) -> None:
        """Notify all registered callbacks about a new pool."""
        for callback in self._pool_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(pool_info)
                else:
                    callback(pool_info)
            except Exception as e:
                logger.error(f"Error in pool callback: {str(e)}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        return {
            "running": self._running,
            "pools_detected": self.pools_detected,
            "active_subscriptions": len(self._subscriptions),
            "subscribed_dexes": sorted(set(self._subscriptions.values())),
            "last_pool_detected_ago": (
                time.time() - self.last_pool_time
                if self.last_pool_time > 0 else None
            ),
        }
