import asyncio

import pytest

from bot.risk_manager import RiskManager
from utils.security import SecurityChecker


def test_stop_loss_triggers():
    rm = RiskManager(trade_cooldown_seconds=0, stop_loss_percent=50)
    rm.open_position("tok", "pool", entry_price=1.0, amount_tokens=1.0, amount_sol=1.0)
    assert rm.update_position_price("tok", 0.4)[0] == "STOP_LOSS"


def test_daily_stats_roll_over_at_new_day():
    rm = RiskManager(trade_cooldown_seconds=0, daily_loss_limit_sol=1.0)
    rm.today_stats.date = "2000-01-01"
    rm.today_stats.total_pnl_sol = -5.0
    can_open, _ = rm.can_open_position(0.1)
    assert can_open
    assert rm.today_stats.total_pnl_sol == 0.0


def test_daily_loss_limit_blocks_trading():
    rm = RiskManager(trade_cooldown_seconds=0, daily_loss_limit_sol=1.0)
    rm.today_stats.total_pnl_sol = -1.0
    assert rm.can_open_position(0.1) == (False, "Daily loss limit reached")


def test_security_check_handles_missing_values():
    pool_info = {"initial_liquidity_sol": None, "creation_timestamp": 0}
    result = asyncio.run(SecurityChecker().analyze_token("tok", pool_info, {"name": None, "decimals": None}))
    assert result.is_safe is False  # Holder analysis is still a placeholder


def test_parse_bool_rejects_typos():
    import argparse
    from main import parse_bool

    assert parse_bool("False") is False
    assert parse_bool("true") is True
    with pytest.raises(argparse.ArgumentTypeError):
        parse_bool("ture")


def test_production_requires_wallet_key(monkeypatch):
    from config.settings import Settings

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("WALLET_PRIVATE_KEY", "")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
