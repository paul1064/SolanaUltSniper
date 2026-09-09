"""
Risk Manager for the Solana Sniper Bot.

Implements comprehensive risk management including:
- Position sizing
- Stop-loss enforcement
- Take-profit targets
- Daily loss limits
- Portfolio balance monitoring
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime, date
import time

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a trading position."""
    
    token_address: str
    pool_address: str
    entry_price: float
    amount_tokens: float
    amount_sol_invested: float
    entry_timestamp: float
    
    # Current state
    current_price: float = 0.0
    last_update: float = 0.0
    
    # Exit targets
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    
    @property
    def unrealized_pnl_sol(self) -> float:
        """Calculate unrealized PnL in SOL."""
        if self.current_price == 0 or self.entry_price == 0:
            return 0.0
        
        current_value_sol = (self.amount_tokens * self.current_price)
        return current_value_sol - self.amount_sol_invested
    
    @property
    def pnl_percent(self) -> float:
        """Calculate PnL percentage."""
        if self.amount_sol_invested == 0:
            return 0.0
        
        return (self.unrealized_pnl_sol / self.amount_sol_invested) * 100


@dataclass
class DailyStats:
    """Daily trading statistics."""
    
    date: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_sol: float = 0.0
    total_volume_sol: float = 0.0
    best_trade_sol: float = 0.0
    worst_trade_sol: float = 0.0


class RiskManager:
    """
    Comprehensive risk management system.
    
    Features:
    - Per-position stop-loss and take-profit
    - Daily loss limits
    - Maximum position sizing
    - Portfolio exposure limits
    - Trade cooldown periods
    """
    
    def __init__(
        self,
        max_loss_per_token_sol: float = 0.05,
        daily_loss_limit_sol: float = 1.0,
        max_position_size_sol: float = 1.0,
        max_total_exposure_sol: float = 5.0,
        take_profit_percent: float = 100.0,
        stop_loss_percent: float = 50.0,
        trade_cooldown_seconds: int = 60,
    ):
        """
        Initialize risk manager.
        
        Args:
            max_loss_per_token_sol: Maximum loss allowed per token
            daily_loss_limit_sol: Daily loss limit before stopping
            max_position_size_sol: Maximum SOL per position
            max_total_exposure_sol: Maximum total SOL in all positions
            take_profit_percent: Default take-profit percentage
            stop_loss_percent: Default stop-loss percentage
            trade_cooldown_seconds: Cooldown between trades
        """
        self.max_loss_per_token_sol = max_loss_per_token_sol
        self.daily_loss_limit_sol = daily_loss_limit_sol
        self.max_position_size_sol = max_position_size_sol
        self.max_total_exposure_sol = max_total_exposure_sol
        self.take_profit_percent = take_profit_percent
        self.stop_loss_percent = stop_loss_percent
        self.trade_cooldown_seconds = trade_cooldown_seconds
        
        # Active positions
        self.positions: Dict[str, Position] = {}
        
        # Daily statistics
        self.today_stats = DailyStats(date=date.today().isoformat())
        
        # Cooldown tracking
        self.last_trade_time: float = 0.0
        
        # Historical performance
        self.total_pnl_sol: float = 0.0
        self.total_trades: int = 0
    
    def can_open_position(self, amount_sol: float) -> tuple[bool, str]:
        """
        Check if a new position can be opened.
        
        Args:
            amount_sol: Amount of SOL to invest
            
        Returns:
            Tuple of (can_open, reason)
        """
        # Check daily loss limit
        if self.today_stats.total_pnl_sol < -self.daily_loss_limit_sol:
            return False, "Daily loss limit reached"
        
        # Check position size
        if amount_sol > self.max_position_size_sol:
            return False, f"Position size exceeds maximum ({amount_sol} > {self.max_position_size_sol})"
        
        # Check total exposure
        current_exposure = sum(p.amount_sol_invested for p in self.positions.values())
        if current_exposure + amount_sol > self.max_total_exposure_sol:
            return False, f"Total exposure would exceed limit"
        
        # Check cooldown
        time_since_last_trade = time.time() - self.last_trade_time
        if time_since_last_trade < self.trade_cooldown_seconds:
            remaining = self.trade_cooldown_seconds - time_since_last_trade
            return False, f"Trade cooldown active ({remaining:.0f}s remaining)"
        
        return True, "OK"
    
    def calculate_exit_targets(
        self,
        entry_price: float,
        amount_sol: float,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate take-profit and stop-loss prices.
        
        Args:
            entry_price: Entry price in SOL per token
            amount_sol: Amount of SOL invested
            
        Returns:
            Tuple of (take_profit_price, stop_loss_price)
        """
        take_profit_price = entry_price * (1 + self.take_profit_percent / 100)
        stop_loss_price = entry_price * (1 - self.stop_loss_percent / 100)
        
        return take_profit_price, stop_loss_price
    
    def open_position(
        self,
        token_address: str,
        pool_address: str,
        entry_price: float,
        amount_tokens: float,
        amount_sol: float,
    ) -> Optional[Position]:
        """
        Open a new trading position.
        
        Args:
            token_address: Token mint address
            pool_address: Liquidity pool address
            entry_price: Entry price in SOL per token
            amount_tokens: Amount of tokens purchased
            amount_sol: Amount of SOL invested
            
        Returns:
            Position object if successful, None otherwise
        """
        # Verify we can open this position
        can_open, reason = self.can_open_position(amount_sol)
        if not can_open:
            logger.warning(f"Cannot open position: {reason}")
            return None
        
        current_time = time.time()
        
        # Calculate exit targets
        take_profit, stop_loss = self.calculate_exit_targets(entry_price, amount_sol)
        
        # Create position
        position = Position(
            token_address=token_address,
            pool_address=pool_address,
            entry_price=entry_price,
            amount_tokens=amount_tokens,
            amount_sol_invested=amount_sol,
            entry_timestamp=current_time,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
            last_update=current_time,
        )
        
        # Store position
        self.positions[token_address] = position
        self.last_trade_time = current_time
        
        logger.info(
            f"Opened position: {token_address[:8]}... @ {entry_price:.8f} SOL | "
            f"TP: {take_profit:.8f} | SL: {stop_loss:.8f}"
        )
        
        return position
    
    def update_position_price(
        self,
        token_address: str,
        current_price: float,
    ) -> Optional[tuple[str, float]]:
        """
        Update the current price for a position and check for exits.
        
        Args:
            token_address: Token mint address
            current_price: Current price in SOL per token
            
        Returns:
            Tuple of (action, pnl) if exit triggered, None otherwise
            action is either 'TAKE_PROFIT', 'STOP_LOSS', or None
        """
        position = self.positions.get(token_address)
        if not position:
            return None
        
        position.current_price = current_price
        position.last_update = time.time()
        
        # Check for take-profit
        if position.take_profit_price and current_price >= position.take_profit_price:
            pnl = position.unrealized_pnl_sol
            logger.info(
                f"🎯 TAKE PROFIT triggered for {token_address[:8]}... | "
                f"PnL: {pnl:.4f} SOL ({position.pnl_percent:.1f}%)"
            )
            return ("TAKE_PROFIT", pnl)
        
        # Check for stop-loss
        if position.stop_loss_price and current_price <= position.stop_loss_price:
            pnl = position.unrealized_pnl_sol
            logger.warning(
                f"🛑 STOP LOSS triggered for {token_address[:8]}... | "
                f"PnL: {pnl:.4f} SOL ({position.pnl_percent:.1f}%)"
            )
            return ("STOP_LOSS", pnl)
        
        # Check for max loss per token
        if position.unrealized_pnl_sol < -self.max_loss_per_token_sol:
            pnl = position.unrealized_pnl_sol
            logger.warning(
                f"⚠️ Max loss reached for {token_address[:8]}... | "
                f"PnL: {pnl:.4f} SOL"
            )
            return ("MAX_LOSS", pnl)
        
        return None
    
    def close_position(
        self,
        token_address: str,
        exit_price: float,
        reason: str = "MANUAL",
    ) -> Optional[float]:
        """
        Close a position.
        
        Args:
            token_address: Token mint address
            exit_price: Exit price in SOL per token
            reason: Reason for closing
            
        Returns:
            Realized PnL in SOL, or None if position not found
        """
        position = self.positions.pop(token_address, None)
        if not position:
            return None
        
        # Calculate realized PnL
        exit_value_sol = position.amount_tokens * exit_price
        pnl_sol = exit_value_sol - position.amount_sol_invested
        pnl_percent = (pnl_sol / position.amount_sol_invested) * 100
        
        # Update statistics
        self.total_pnl_sol += pnl_sol
        self.total_trades += 1
        self.today_stats.total_trades += 1
        self.today_stats.total_pnl_sol += pnl_sol
        self.today_stats.total_volume_sol += position.amount_sol_invested + exit_value_sol
        
        if pnl_sol > 0:
            self.today_stats.winning_trades += 1
        else:
            self.today_stats.losing_trades += 1
        
        self.today_stats.best_trade_sol = max(self.today_stats.best_trade_sol, pnl_sol)
        self.today_stats.worst_trade_sol = min(self.today_stats.worst_trade_sol, pnl_sol)
        
        # Log the result
        emoji = "✅" if pnl_sol > 0 else "❌"
        logger.info(
            f"{emoji} Position closed: {token_address[:8]}... | "
            f"Reason: {reason} | "
            f"PnL: {pnl_sol:.4f} SOL ({pnl_percent:.1f}%)"
        )
        
        return pnl_sol
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get a summary of the current portfolio."""
        total_invested = sum(p.amount_sol_invested for p in self.positions.values())
        total_current_value = sum(
            p.amount_tokens * p.current_price 
            for p in self.positions.values() 
            if p.current_price > 0
        )
        total_unrealized_pnl = total_current_value - total_invested
        
        return {
            "active_positions": len(self.positions),
            "total_invested_sol": total_invested,
            "total_current_value_sol": total_current_value,
            "total_unrealized_pnl_sol": total_unrealized_pnl,
            "today_pnl_sol": self.today_stats.total_pnl_sol,
            "today_trades": self.today_stats.total_trades,
            "total_trades": self.total_trades,
            "lifetime_pnl_sol": self.total_pnl_sol,
            "win_rate": (
                self.today_stats.winning_trades / self.today_stats.total_trades * 100
                if self.today_stats.total_trades > 0 else 0
            ),
        }
    
    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at midnight UTC)."""
        self.today_stats = DailyStats(date=date.today().isoformat())
        logger.info("Daily statistics reset")
