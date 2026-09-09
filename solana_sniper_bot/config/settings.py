"""
Configuration settings for the Solana Sniper Bot.

Security Best Practice:
- All sensitive data (private keys, API keys) are loaded from environment variables
- Never hardcode credentials in this file or any version-controlled file
- Use .env file for local development (never commit .env!)
- Use proper secrets management in production
"""

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Security Notes:
    - WALLET_PRIVATE_KEY must be set via environment variable, never hardcoded
    - DRY_RUN is enabled by default to prevent accidental real trades
    - Always verify settings before running in production mode
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # =========================================================================
    # SOLANA RPC CONFIGURATION
    # =========================================================================
    
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="Solana RPC endpoint URL"
    )
    
    solana_ws_url: str = Field(
        default="wss://api.mainnet-beta.solana.com",
        description="Solana WebSocket endpoint URL"
    )
    
    # Premium RPC providers (optional but recommended for production)
    quicknode_url: Optional[str] = Field(default=None)
    helius_url: Optional[str] = Field(default=None)
    triton_url: Optional[str] = Field(default=None)
    
    # =========================================================================
    # WALLET CONFIGURATION
    # =========================================================================
    
    wallet_private_key: str = Field(
        default="",
        description="Solana wallet private key (base58 encoded)"
    )
    
    @field_validator("wallet_private_key")
    @classmethod
    def validate_wallet_key(cls, v: str) -> str:
        """Validate that wallet private key is provided when not in dry run mode."""
        # Skip validation in dry run mode
        if os.getenv("DRY_RUN", "true").lower() == "true":
            return v
        
        if not v or len(v) < 32:
            raise ValueError(
                "WALLET_PRIVATE_KEY must be set for production trading. "
                "Set DRY_RUN=true if you want to test without a real wallet."
            )
        return v
    
    # =========================================================================
    # TRADING PARAMETERS
    # =========================================================================
    
    buy_amount_sol: float = Field(
        default=0.1,
        ge=0.001,
        le=100.0,
        description="Amount of SOL to use for each buy order"
    )
    
    max_slippage_bps: int = Field(
        default=500,
        ge=0,
        le=10000,
        description="Maximum slippage in basis points (500 = 5%)"
    )
    
    priority_fee_lamports: int = Field(
        default=100000,
        ge=0,
        description="Priority fee in lamports for transaction processing"
    )
    
    # =========================================================================
    # SECURITY & RISK MANAGEMENT
    # =========================================================================
    
    min_liquidity_sol: float = Field(
        default=1000.0,
        ge=0,
        description="Minimum pool liquidity in SOL to consider trading"
    )
    
    max_liquidity_sol: float = Field(
        default=100000.0,
        ge=0,
        description="Maximum pool liquidity in SOL to consider trading"
    )
    
    max_loss_per_token_sol: float = Field(
        default=0.05,
        ge=0,
        description="Maximum loss per token in SOL before stop-loss triggers"
    )
    
    daily_loss_limit_sol: float = Field(
        default=1.0,
        ge=0,
        description="Daily loss limit in SOL before bot stops trading"
    )
    
    # Token safety checks
    check_mint_authority: bool = Field(
        default=True,
        description="Check if mint authority is disabled (safety feature)"
    )
    
    check_freeze_authority: bool = Field(
        default=True,
        description="Check if freeze authority is disabled (safety feature)"
    )
    
    min_holders: int = Field(
        default=10,
        ge=1,
        description="Minimum number of token holders required"
    )
    
    max_top_holder_percent: float = Field(
        default=30.0,
        ge=0,
        le=100,
        description="Maximum percentage held by top holder (anti-whale protection)"
    )
    
    # =========================================================================
    # DEX CONFIGURATION
    # =========================================================================
    
    monitor_raydium: bool = Field(default=True)
    monitor_orca: bool = Field(default=True)
    monitor_pumpfun: bool = Field(default=True)
    
    # =========================================================================
    # ADVANCED FEATURES
    # =========================================================================
    
    enable_jito: bool = Field(
        default=False,
        description="Enable Jito bundle submission for MEV protection"
    )
    
    jito_auth_keypair: Optional[str] = Field(
        default=None,
        description="Jito authentication keypair (required if enable_jito=True)"
    )
    
    enable_auto_sell: bool = Field(
        default=True,
        description="Enable automatic take-profit and stop-loss selling"
    )
    
    take_profit_percent: float = Field(
        default=100.0,
        ge=0,
        description="Take profit percentage (100 = 2x price)"
    )
    
    stop_loss_percent: float = Field(
        default=50.0,
        ge=0,
        le=100,
        description="Stop loss percentage (50 = -50% price)"
    )
    
    # =========================================================================
    # BOT SETTINGS
    # =========================================================================
    
    dry_run: bool = Field(
        default=True,
        description="If True, bot simulates trades without executing them"
    )
    
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @property
    def effective_rpc_url(self) -> str:
        """Get the best available RPC URL based on configuration."""
        if self.helius_url:
            return self.helius_url
        if self.quicknode_url:
            return self.quicknode_url
        if self.triton_url:
            return self.triton_url
        return self.solana_rpc_url
    
    @property
    def is_production(self) -> bool:
        """Check if bot is running in production mode (real trades)."""
        return not self.dry_run
    
    def validate_for_production(self) -> None:
        """
        Validate all settings for production mode.
        
        Raises:
            ValueError: If any critical setting is misconfigured
        """
        if self.is_production:
            errors = []
            
            if not self.wallet_private_key:
                errors.append("WALLET_PRIVATE_KEY is required for production")
            
            if self.buy_amount_sol > 1.0:
                errors.append("Consider reducing BUY_AMOUNT_SOL for safety")
            
            if not self.check_mint_authority:
                errors.append("CHECK_MINT_AUTHORITY should be enabled for safety")
            
            if errors:
                raise ValueError(
                    f"Production configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
                )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global settings
    settings = Settings()
    return settings
