"""
Pool Monitor for the Solana Sniper Bot.

Monitors DEXes (Raydium, Orca, Pump.fun) for new liquidity pools
using WebSocket subscriptions for real-time detection.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    
    Uses WebSocket subscriptions for instant detection.
    """
    
    # Known DEX program IDs on mainnet
    RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    PUMPFUN_MAIN = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    
    # SPL Token Program
    TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    
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
        self.monitor_raydium = monitor_raydium
        self.monitor_orca = monitor_orca
        self.monitor_pumpfun = monitor_pumpfun
        
        # Callbacks for new pools
        self._pool_callbacks: List[Callable] = []
        
        # Connection state
        self._ws_connection = None
        self._subscriptions: Dict[str, int] = {}
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
        """Start monitoring for new pools."""
        if self._running:
            logger.warning("PoolMonitor already running")
            return
        
        self._running = True
        logger.info("Starting PoolMonitor...")
        
        try:
            # Connect to WebSocket
            await self._connect_websocket()
            
            # Subscribe to DEX programs
            if self.monitor_raydium:
                await self._subscribe_to_program(
                    self.RAYDIUM_AMM_V4,
                    "raydium",
                )
            
            if self.monitor_orca:
                await self._subscribe_to_program(
                    self.ORCA_WHIRLPOOL,
                    "orca",
                )
            
            if self.monitor_pumpfun:
                await self._subscribe_to_program(
                    self.PUMPFUN_MAIN,
                    "pumpfun",
                )
            
            # Start listening for events
            await self._listen_for_events()
            
        except Exception as e:
            logger.error(f"PoolMonitor error: {str(e)}")
            self._running = False
            raise
    
    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        
        if self._ws_connection:
            await self._ws_connection.close()
            self._ws_connection = None
        
        logger.info("PoolMonitor stopped")
    
    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection."""
        from solana.rpc.websocket_api import connect
        
        logger.info(f"Connecting to WebSocket: {self.ws_url[:30]}...")
        
        self._ws_connection = await connect(self.ws_url).__aenter__()
        
        logger.info("WebSocket connected")
    
    async def _subscribe_to_program(
        self,
        program_id: str,
        dex_name: str,
    ) -> None:
        """
        Subscribe to logs for a DEX program.
        
        Args:
            program_id: Program public key (as string)
            dex_name: Name of the DEX
        """
        from solders.pubkey import Pubkey
        
        logger.info(f"Subscribing to {dex_name} program: {program_id}")
        
        try:
            # Convert string to Pubkey object
            program_pubkey = Pubkey.from_string(program_id)
            
            # Subscribe to program logs
            subscription = await self._ws_connection.program_subscribe(
                program_pubkey,
                commitment="confirmed",
            )
            
            self._subscriptions[dex_name] = subscription
            
            logger.info(f"Subscribed to {dex_name} (subscription ID: {subscription})")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {dex_name}: {str(e)}")
    
    async def _listen_for_events(self) -> None:
        """Listen for log events from subscribed programs."""
        logger.info("Listening for pool creation events...")
        
        while self._running:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    self._ws_connection.recv(),
                    timeout=30.0,
                )
                
                # Process the message
                await self._process_log_message(message)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                continue
            except Exception as e:
                error_msg = str(e)
                # Ignore WebSocket close frame errors (normal behavior)
                if "sent 1000" in error_msg and "received 1000" in error_msg:
                    logger.debug(f"WebsSocket keepalive: {error_msg}")
                else:
                    logger.error(f"Error processing message: {error_msg}")
                await asyncio.sleep(0.5)
    
    async def _process_log_message(self, message: Any) -> None:
        """
        Process a WebSocket log message.
        
        Args:
            message: Raw WebSocket message
        """
        try:
            # Parse message structure
            # Format depends on Solana WS API
            if not hasattr(message, '__getitem__'):
                return
            
            # Extract log data
            params = message[0] if len(message) > 0 else None
            if not params or 'value' not in params:
                return
            
            value = params['value']
            logs = value.get('logs', [])
            signature = value.get('signature', '')
            
            # Check if this is a pool creation event
            pool_info = await self._parse_pool_creation(logs, signature)
            
            if pool_info:
                self.pools_detected += 1
                self.last_pool_time = asyncio.get_event_loop().time()
                
                logger.info(
                    f"🆕 New pool detected on {pool_info.dex}! | "
                    f"Token: {pool_info.token_address[:8]}... | "
                    f"Liquidity: {pool_info.liquidity_sol:.2f} SOL"
                )
                
                # Notify callbacks
                await self._notify_callbacks(pool_info)
                
        except Exception as e:
            logger.debug(f"Error parsing log message: {str(e)}")
    
    async def _parse_pool_creation(
        self,
        logs: List[str],
        signature: str,
    ) -> Optional[PoolInfo]:
        """
        Parse logs to detect pool creation.
        
        This is a simplified implementation. In production, you would:
        1. Parse actual log messages from each DEX
        2. Extract pool state from account data
        3. Fetch token metadata
        
        Args:
            logs: Transaction log messages
            signature: Transaction signature
            
        Returns:
            PoolInfo if pool creation detected, None otherwise
        """
        # Simplified detection logic
        # In production, implement proper log parsing for each DEX
        
        # Look for initialization patterns
        for log in logs:
            if 'initialize' in log.lower() or 'init' in log.lower():
                # Found potential pool initialization
                # Extract addresses from logs (simplified)
                
                return PoolInfo(
                    pool_address=f"pool_{signature[:40]}",
                    token_address=f"token_{signature[:40]}",
                    base_mint="So11111111111111111111111111111111111111112",  # Wrapped SOL
                    quote_mint=f"token_{signature[:40]}",
                    liquidity_sol=1000.0,  # Placeholder
                    liquidity_tokens=1000000.0,  # Placeholder
                    creation_timestamp=asyncio.get_event_loop().time(),
                    dex="raydium",  # Would be determined from program ID
                    program_id=self.RAYDIUM_AMM_V4,
                )
        
        return None
    
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
            "subscribed_dexes": list(self._subscriptions.keys()),
            "last_pool_detected_ago": (
                asyncio.get_event_loop().time() - self.last_pool_time
                if self.last_pool_time > 0 else None
            ),
        }
