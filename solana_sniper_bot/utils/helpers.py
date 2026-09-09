"""
Helper utilities for the Solana Sniper Bot.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def format_sol_amount(lamports: int) -> str:
    """
    Convert lamports to human-readable SOL amount.
    
    Args:
        lamports: Amount in lamports (1 SOL = 1,000,000,000 lamports)
        
    Returns:
        Formatted string with SOL amount
    """
    sol_amount = lamports / 1_000_000_000
    
    if sol_amount >= 1000:
        return f"{sol_amount:,.2f} SOL"
    elif sol_amount >= 1:
        return f"{sol_amount:.4f} SOL"
    elif sol_amount >= 0.001:
        return f"{sol_amount:.6f} SOL"
    else:
        return f"{sol_amount:.9f} SOL"


def format_lamports(sol_amount: float) -> int:
    """
    Convert SOL amount to lamports.
    
    Args:
        sol_amount: Amount in SOL
        
    Returns:
        Amount in lamports
    """
    return int(sol_amount * 1_000_000_000)


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """
    Format a Unix timestamp as human-readable datetime.
    
    Args:
        timestamp: Unix timestamp (uses current time if None)
        
    Returns:
        Formatted datetime string
    """
    if timestamp is None:
        dt = datetime.now()
    else:
        dt = datetime.fromtimestamp(timestamp)
    
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def calculate_price_impact(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee_bps: int = 30,
) -> float:
    """
    Calculate price impact for a swap using constant product formula.
    
    Formula: x * y = k
    
    Args:
        amount_in: Input amount (in token decimals)
        reserve_in: Reserve of input token in pool
        reserve_out: Reserve of output token in pool
        fee_bps: Trading fee in basis points (default 30 = 0.3%)
        
    Returns:
        Price impact as percentage (e.g., 5.2 means 5.2% impact)
    """
    # Apply fee to input amount
    fee_multiplier = 1 - (fee_bps / 10000)
    amount_in_with_fee = int(amount_in * fee_multiplier)
    
    # Calculate output amount using constant product formula
    # out = (amount_in * reserve_out) / (reserve_in + amount_in)
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee
    
    if denominator == 0:
        logger.warning("Division by zero in price impact calculation")
        return 100.0
    
    actual_output = numerator // denominator
    
    # Calculate expected output without slippage
    # spot_price = reserve_out / reserve_in
    # expected_output = amount_in * spot_price
    if reserve_in == 0:
        return 100.0
    
    spot_price = reserve_out / reserve_in
    expected_output = amount_in * spot_price
    
    # Price impact = (expected - actual) / expected * 100
    if expected_output == 0:
        return 0.0
    
    price_impact = ((expected_output - actual_output) / expected_output) * 100
    
    return max(0.0, price_impact)


def calculate_minimum_received(
    amount_out: int,
    slippage_bps: int,
) -> int:
    """
    Calculate minimum amount received after slippage.
    
    Args:
        amount_out: Expected output amount
        slippage_bps: Maximum allowed slippage in basis points
        
    Returns:
        Minimum acceptable output amount
    """
    slippage_multiplier = 1 - (slippage_bps / 10000)
    return int(amount_out * slippage_multiplier)


def parse_token_amount(amount_str: str, decimals: int) -> int:
    """
    Parse a token amount string to raw units.
    
    Args:
        amount_str: Amount as string (e.g., "1.5")
        decimals: Token decimal places
        
    Returns:
        Raw token amount
    """
    from decimal import Decimal, getcontext
    
    # Set precision high enough for crypto calculations
    getcontext().prec = 50
    
    amount_decimal = Decimal(amount_str)
    multiplier = Decimal(10) ** decimals
    
    return int(amount_decimal * multiplier)


def shorten_address(address: str, chars: int = 4) -> str:
    """
    Shorten a Solana address for display.
    
    Args:
        address: Full base58 address
        chars: Number of characters to show at start and end
        
    Returns:
        Shortened address (e.g., "5xG...abc")
    """
    if len(address) <= chars * 2 + 3:
        return address
    
    return f"{address[:chars]}...{address[-chars:]}"


def calculate_priority_fee(
    base_fee: int,
    urgency_multiplier: float = 1.0,
) -> int:
    """
    Calculate priority fee based on network conditions.
    
    Args:
        base_fee: Base priority fee in lamports
        urgency_multiplier: Multiplier for urgent transactions (1.0-10.0)
        
    Returns:
        Priority fee in lamports
    """
    urgency_multiplier = max(1.0, min(10.0, urgency_multiplier))
    return int(base_fee * urgency_multiplier)


def get_current_timestamp() -> float:
    """Get current Unix timestamp."""
    return datetime.now().timestamp()


def is_within_time_window(
    timestamp: float,
    window_seconds: int,
    reference_time: Optional[float] = None,
) -> bool:
    """
    Check if a timestamp is within a time window.
    
    Args:
        timestamp: Timestamp to check
        window_seconds: Window size in seconds
        reference_time: Reference timestamp (uses current time if None)
        
    Returns:
        True if within window
    """
    if reference_time is None:
        reference_time = get_current_timestamp()
    
    return abs(timestamp - reference_time) <= window_seconds
