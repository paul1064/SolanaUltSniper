"""
Main Sniper Bot implementation.

Orchestrates all components:
- Pool monitoring
- Token filtering
- Security analysis
- Trade execution
- Risk management
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

# Use absolute imports to avoid issues when running as script
from bot.pool_monitor import PoolMonitor, PoolInfo
from bot.filters import TokenFilter, FilterResult
from bot.executor import TradeExecutor
from bot.risk_manager import RiskManager
from utils.security import SecurityChecker, TokenSafetyResult
from config.settings import Settings

logger = logging.getLogger(__name__)


class SniperBot:
    """
    Main Solana Sniper Bot.
    
    Workflow:
    1. Monitor DEXes for new pools (PoolMonitor)
    2. Filter tokens quickly (TokenFilter)
    3. Deep security analysis (SecurityChecker)
    4. Check risk limits (RiskManager)
    5. Execute trade (TradeExecutor)
    6. Monitor position & auto-sell (RiskManager + Executor)
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize the sniper bot.
        
        Args:
            settings: Bot configuration settings
        """
        self.settings = settings
        
        logger.info("Initializing SniperBot...")
        logger.info(f"Mode: {'PRODUCTION' if settings.is_production else 'DRY RUN'}")
        
        # Initialize components
        self.pool_monitor = PoolMonitor(
            ws_url=settings.solana_ws_url,
            rpc_url=settings.effective_rpc_url,
            monitor_raydium=settings.monitor_raydium,
            monitor_orca=settings.monitor_orca,
            monitor_pumpfun=settings.monitor_pumpfun,
        )
        
        self.token_filter = TokenFilter(
            min_liquidity_sol=settings.min_liquidity_sol,
            max_liquidity_sol=settings.max_liquidity_sol,
            check_metadata=True,
        )
        
        self.security_checker = SecurityChecker(
            min_holders=settings.min_holders,
            max_top_holder_percent=settings.max_top_holder_percent,
            check_mint_authority=settings.check_mint_authority,
            check_freeze_authority=settings.check_freeze_authority,
        )
        
        self.risk_manager = RiskManager(
            max_loss_per_token_sol=settings.max_loss_per_token_sol,
            daily_loss_limit_sol=settings.daily_loss_limit_sol,
            max_position_size_sol=settings.buy_amount_sol * 2,
            take_profit_percent=settings.take_profit_percent,
            stop_loss_percent=settings.stop_loss_percent,
        )
        
        self.executor = TradeExecutor(
            rpc_url=settings.effective_rpc_url,
            wallet_private_key=settings.wallet_private_key,
            priority_fee_lamports=settings.priority_fee_lamports,
            max_slippage_bps=settings.max_slippage_bps,
            enable_jito=settings.enable_jito,
            jito_auth_keypair=settings.jito_auth_keypair,
            dry_run=settings.dry_run,
        )
        
        # Register callback for new pools
        self.pool_monitor.add_pool_callback(self._on_new_pool)
        
        # State
        self._running = False
        self._stats = {
            "pools_detected": 0,
            "pools_filtered": 0,
            "security_checks_passed": 0,
            "trades_executed": 0,
            "trades_successful": 0,
            "trades_failed": 0,
        }
        
        logger.info("SniperBot initialized successfully")
    
    async def start(self) -> None:
        """Start the sniper bot."""
        if self._running:
            logger.warning("Bot is already running")
            return
        
        logger.info("🚀 Starting SniperBot...")
        
        # Validate production settings if not in dry run
        if self.settings.is_production:
            try:
                self.settings.validate_for_production()
            except ValueError as e:
                logger.error(f"Production validation failed: {str(e)}")
                return
        
        self._running = True
        
        # Start pool monitoring (this will block)
        await self.pool_monitor.start()
    
    async def stop(self) -> None:
        """Stop the sniper bot."""
        if not self._running:
            return
        
        logger.info("Stopping SniperBot...")
        self._running = False
        
        await self.pool_monitor.stop()
        await self.executor.close()
        
        logger.info("SniperBot stopped")
    
    async def _on_new_pool(self, pool_info: PoolInfo) -> None:
        """
        Callback when a new pool is detected.
        
        This is the main entry point for the sniping workflow.
        
        Args:
            pool_info: Information about the new pool
        """
        self._stats["pools_detected"] += 1
        
        logger.info(
            f"🔍 Analyzing new pool: {pool_info.token_address[:8]}... | "
            f"DEX: {pool_info.dex} | Liquidity: {pool_info.liquidity_sol:.2f} SOL"
        )
        
        try:
            # Step 1: Fast filtering
            filter_result = await self.token_filter.filter_token(
                token_address=pool_info.token_address,
                pool_address=pool_info.pool_address,
                pool_info=self._pool_info_to_dict(pool_info),
            )
            
            if not filter_result.passed:
                self._stats["pools_filtered"] += 1
                logger.info(f"❌ Filter rejected: {filter_result.rejection_reason}")
                return
            
            logger.info("✅ Token passed initial filters")
            
            # Step 2: Deep security analysis
            safety_result = await self.security_checker.analyze_token(
                token_address=pool_info.token_address,
                pool_info=self._pool_info_to_dict(pool_info),
                token_metadata=pool_info.token_metadata,
            )
            
            if not safety_result.is_safe:
                logger.warning(
                    f"❌ Security check failed: {safety_result.get_summary()}"
                )
                for flag in safety_result.risk_flags:
                    logger.warning(f"   ⚠️ {flag}")
                return
            
            self._stats["security_checks_passed"] += 1
            logger.info(f"✅ Security check passed: {safety_result.get_summary()}")
            
            # Step 3: Risk management check
            can_trade, reason = self.risk_manager.can_open_position(
                self.settings.buy_amount_sol
            )
            
            if not can_trade:
                logger.warning(f"⛔ Risk manager blocked trade: {reason}")
                return
            
            # Step 4: Execute buy
            self._stats["trades_executed"] += 1
            
            buy_result = await self.executor.execute_buy(
                pool_address=pool_info.pool_address,
                token_address=pool_info.token_address,
                sol_amount=self.settings.buy_amount_sol,
                min_tokens_out=self._calculate_min_tokens_out(pool_info),
            )
            
            if buy_result.success:
                self._stats["trades_successful"] += 1
                
                logger.info(
                    f"✅ BUY EXECUTED! TX: {buy_result.transaction_signature}"
                )
                
                # Open position in risk manager
                entry_price = self._calculate_entry_price(pool_info)
                self.risk_manager.open_position(
                    token_address=pool_info.token_address,
                    pool_address=pool_info.pool_address,
                    entry_price=entry_price,
                    amount_tokens=buy_result.token_amount,
                    amount_sol=buy_result.sol_amount,
                )
                
                # Start monitoring position if auto-sell enabled
                if self.settings.enable_auto_sell:
                    asyncio.create_task(
                        self._monitor_position(pool_info.token_address)
                    )
                
            else:
                self._stats["trades_failed"] += 1
                logger.error(f"❌ Trade execution failed: {buy_result.error_message}")
                
        except Exception as e:
            logger.exception(f"Error processing pool: {str(e)}")
    
    async def _monitor_position(self, token_address: str) -> None:
        """
        Monitor a position and auto-sell when targets are hit.
        
        Args:
            token_address: Token mint address
        """
        logger.info(f"👁️ Monitoring position: {token_address[:8]}...")
        
        while self._running and token_address in self.risk_manager.positions:
            try:
                # Get current price (in production, fetch from RPC/DEX)
                current_price = await self._get_current_price(token_address)
                
                if current_price > 0:
                    # Check if we should exit
                    exit_signal = self.risk_manager.update_position_price(
                        token_address=token_address,
                        current_price=current_price,
                    )
                    
                    if exit_signal:
                        action, pnl = exit_signal
                        
                        # Execute sell
                        position = self.risk_manager.positions.get(token_address)
                        if position:
                            sell_result = await self.executor.execute_sell(
                                pool_address=position.pool_address,
                                token_address=token_address,
                                token_amount=position.amount_tokens,
                                min_sol_out=position.amount_sol_invested * 0.9,  # 90% of entry
                            )
                            
                            if sell_result.success:
                                self.risk_manager.close_position(
                                    token_address=token_address,
                                    exit_price=current_price,
                                    reason=action,
                                )
                                break
                
                # Wait before next check
                await asyncio.sleep(5.0)
                
            except Exception as e:
                logger.error(f"Error monitoring position: {str(e)}")
                await asyncio.sleep(5.0)
    
    async def _get_current_price(self, token_address: str) -> float:
        """
        Get current token price in SOL.
        
        In production, this would query:
        - DEX pool reserves
        - Price oracle (Pyth, Switchboard)
        - Jupiter API
        
        For now, returns placeholder.
        """
        # Placeholder - implement with actual price fetching
        return 0.0
    
    def _pool_info_to_dict(self, pool_info: PoolInfo) -> Dict[str, Any]:
        """Convert PoolInfo to dictionary for other components."""
        return {
            "pool_address": pool_info.pool_address,
            "token_address": pool_info.token_address,
            "liquidity_sol": pool_info.liquidity_sol,
            "creation_timestamp": pool_info.creation_timestamp,
            "dex": pool_info.dex,
            "program_id": pool_info.program_id,
            "token_metadata": pool_info.token_metadata,
            "creator_address": pool_info.creator_address,
            "initial_liquidity_sol": pool_info.initial_liquidity_sol,
        }
    
    def _calculate_min_tokens_out(self, pool_info: PoolInfo) -> float:
        """Calculate minimum tokens to receive based on slippage."""
        # Simplified calculation
        # In production: use actual pool reserves and swap formula
        base_amount = pool_info.liquidity_tokens / pool_info.liquidity_sol
        slippage_factor = 1 - (self.settings.max_slippage_bps / 10000)
        return base_amount * self.settings.buy_amount_sol * slippage_factor
    
    def _calculate_entry_price(self, pool_info: PoolInfo) -> float:
        """Calculate entry price in SOL per token."""
        if pool_info.liquidity_tokens == 0:
            return 0.0
        return pool_info.liquidity_sol / pool_info.liquidity_tokens
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics."""
        portfolio = self.risk_manager.get_portfolio_summary()
        
        return {
            **self._stats,
            "running": self._running,
            "mode": "production" if self.settings.is_production else "dry_run",
            "portfolio": portfolio,
            "uptime_seconds": (
                datetime.now().timestamp() - self._start_time
                if hasattr(self, "_start_time") else 0
            ),
        }
