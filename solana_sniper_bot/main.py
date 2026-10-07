#!/usr/bin/env python3
"""
Solana Token Sniper Bot - Main Entry Point

This bot monitors Solana DEXes for new token launches and automatically
executes trades based on configurable criteria and risk management rules.

⚠️ WARNING: Trading cryptocurrencies is extremely risky. Only use capital
you can afford to lose. This software is provided as-is without warranty.

Usage:
    python main.py [--dry-run] [--buy-amount SOL] [--min-liquidity SOL]
    
Examples:
    # Run in dry-run mode (no real trades)
    python main.py
    
    # Run with custom parameters
    python main.py --buy-amount 0.5 --min-liquidity 2000
    
    # Run in production mode (REAL TRADES!)
    export WALLET_PRIVATE_KEY="your_key_here"
    python main.py --dry-run false
"""

import argparse
import asyncio
import contextlib
import logging
import signal
import sys

# Configure logging
def setup_logging(log_level: str = "INFO") -> None:
    """Setup colored logging."""
    try:
        import colorlog
        
        # Create formatter with color support
        formatter = colorlog.ColoredFormatter(
            fmt='%(log_color)s[%(asctime)s] %(levelname)s:%(reset)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        
    except ImportError:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=[handler],
    )


async def main(args: argparse.Namespace) -> None:
    """Main entry point."""
    from config.settings import reload_settings
    from bot.sniper import SniperBot
    from bot.pool_monitor import redact_url
    
    # Reload settings to pick up command-line overrides
    settings = reload_settings()
    
    # Apply command-line overrides
    if args.dry_run is not None:
        settings.dry_run = args.dry_run
    
    if args.buy_amount is not None:
        settings.buy_amount_sol = args.buy_amount
    
    if args.min_liquidity is not None:
        settings.min_liquidity_sol = args.min_liquidity
    
    if args.log_level:
        settings.log_level = args.log_level
    
    # Setup logging with configured level
    setup_logging(settings.log_level)
    
    logger = logging.getLogger(__name__)
    
    # Display banner
    print("""
╔═══════════════════════════════════════════════════════════╗
║           🎯 SOLANA TOKEN SNIPER BOT 🎯                   ║
║                                                           ║
║   High-speed automated trading for new Solana tokens      ║
║                                                           ║
║   ⚠️  USE AT YOUR OWN RISK - CRYPTO TRADING IS DANGEROUS  ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Log configuration summary
    logger.info("Configuration:")
    logger.info(f"  Mode: {'PRODUCTION (REAL TRADES)' if settings.is_production else 'DRY RUN'}")
    logger.info(f"  RPC URL: {redact_url(settings.effective_rpc_url)}")
    logger.info(f"  Buy Amount: {settings.buy_amount_sol} SOL")
    logger.info(f"  Min Liquidity: {settings.min_liquidity_sol} SOL")
    logger.info(f"  Max Slippage: {settings.max_slippage_bps / 100:.2f}%")
    logger.info(f"  Priority Fee: {settings.priority_fee_lamports} lamports")
    logger.info(f"  Take Profit: {settings.take_profit_percent}%")
    logger.info(f"  Stop Loss: {settings.stop_loss_percent}%")
    
    if settings.is_production:
        logger.warning("=" * 60)
        logger.warning("⚠️  PRODUCTION MODE - REAL MONEY WILL BE TRADED! ⚠️")
        logger.warning("=" * 60)
        
        # Validate production settings
        try:
            settings.validate_for_production()
        except ValueError as e:
            logger.error(f"Production validation failed: {str(e)}")
            sys.exit(1)
    else:
        logger.info("=" * 60)
        logger.info("✅ DRY RUN MODE - No real trades will be executed")
        logger.info("=" * 60)
    
    # Initialize bot
    bot = SniperBot(settings)
    
    # Setup shutdown handlers
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    def request_shutdown(sig: signal.Signals) -> None:
        logger.info(f"Received {sig.name}, shutting down...")
        shutdown_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown, sig)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(shutdown_event.set))
    
    # Start bot
    try:
        logger.info("Starting bot...")
        
        # Run bot in background task
        bot_task = asyncio.create_task(bot.start())
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        # Wait for a shutdown signal, or for the bot to exit on its own (e.g. fatal error)
        await asyncio.wait({bot_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)
        shutdown_task.cancel()
        
        # Stop bot
        logger.info("Stopping bot...")
        await bot.stop()
        
        if bot_task.done():
            bot_task.result()  # Re-raise a fatal error from the bot
        else:
            bot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot_task
        
        # Print final statistics
        stats = bot.get_stats()
        logger.info("=" * 60)
        logger.info("FINAL STATISTICS:")
        logger.info(f"  Pools Detected: {stats['pools_detected']}")
        logger.info(f"  Pools Filtered: {stats['pools_filtered']}")
        logger.info(f"  Security Checks Passed: {stats['security_checks_passed']}")
        logger.info(f"  Trades Executed: {stats['trades_executed']}")
        logger.info(f"  Trades Successful: {stats['trades_successful']}")
        logger.info(f"  Trades Failed: {stats['trades_failed']}")
        
        portfolio = stats['portfolio']
        logger.info(f"  Active Positions: {portfolio['active_positions']}")
        logger.info(f"  Today's PnL: {portfolio['today_pnl_sol']:.4f} SOL")
        logger.info(f"  Win Rate: {portfolio['win_rate']:.1f}%")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.exception(f"Fatal error: {str(e)}")
        await bot.stop()
        sys.exit(1)


def parse_bool(value: str) -> bool:
    """Parse a strict boolean so a typo can never switch on real trading."""
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got '{value}'")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Solana Token Sniper Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run in dry-run mode
  %(prog)s --dry-run false          # Run in production mode
  %(prog)s --buy-amount 0.5         # Buy 0.5 SOL per trade
  %(prog)s --min-liquidity 5000     # Min 5000 SOL liquidity
        """
    )
    
    parser.add_argument(
        "--dry-run",
        type=parse_bool,
        default=None,
        help="Run in simulation mode (default: True)"
    )
    
    parser.add_argument(
        "--buy-amount",
        type=float,
        default=None,
        help="Amount of SOL to spend per trade"
    )
    
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=None,
        help="Minimum pool liquidity in SOL"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Solana Sniper Bot v1.0.0"
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)
