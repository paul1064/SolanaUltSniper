"""
Security utilities for token safety verification.

This module implements multi-layer security checks to protect against:
- Rug pulls (mint authority still enabled)
- Honeypots (freeze authority, transfer restrictions)
- Whale manipulation (concentrated holdings)
- Liquidity locks verification
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class TokenSafetyResult:
    """Result of token safety analysis."""
    
    is_safe: bool
    score: float  # 0-100, higher is safer
    
    # Safety checks
    mint_authority_disabled: bool = False
    freeze_authority_disabled: bool = False
    liquidity_locked: Optional[bool] = None
    renounced_ownership: Optional[bool] = None
    
    # Holder analysis
    total_holders: int = 0
    top_holder_percent: float = 100.0
    top_10_holders_percent: float = 100.0
    
    # Risk flags
    risk_flags: List[str] = field(default_factory=list)
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_summary(self) -> str:
        """Get a human-readable safety summary."""
        status = "✅ SAFE" if self.is_safe else "❌ UNSAFE"
        return f"{status} (Score: {self.score:.1f}/100) - {len(self.risk_flags)} risk flags"


class SecurityChecker:
    """
    Multi-layer security checker for Solana tokens.
    
    Implements comprehensive safety checks based on best practices
    from successful sniper bot operators and security researchers.
    """
    
    # Weight factors for safety score calculation
    WEIGHTS = {
        "mint_authority": 25,
        "freeze_authority": 20,
        "liquidity_lock": 20,
        "holder_distribution": 15,
        "top_holder_percent": 10,
        "renounced_ownership": 10,
    }
    
    def __init__(
        self,
        min_holders: int = 10,
        max_top_holder_percent: float = 30.0,
        check_mint_authority: bool = True,
        check_freeze_authority: bool = True,
    ):
        """
        Initialize security checker with configurable thresholds.
        
        Args:
            min_holders: Minimum number of holders required
            max_top_holder_percent: Maximum percentage held by top holder
            check_mint_authority: Whether to check mint authority
            check_freeze_authority: Whether to check freeze authority
        """
        self.min_holders = min_holders
        self.max_top_holder_percent = max_top_holder_percent
        self.check_mint_authority = check_mint_authority
        self.check_freeze_authority = check_freeze_authority
    
    async def analyze_token(
        self,
        token_address: str,
        pool_info: Dict[str, Any],
        token_metadata: Optional[Dict[str, Any]] = None,
    ) -> TokenSafetyResult:
        """
        Perform comprehensive security analysis on a token.
        
        Args:
            token_address: The token mint address
            pool_info: Pool information (liquidity, reserves, etc.)
            token_metadata: Optional token metadata
            
        Returns:
            TokenSafetyResult with detailed safety analysis
        """
        risk_flags = []
        score = 100.0
        
        # Extract token info
        token_info = token_metadata or {}
        
        # Check 1: Mint Authority
        mint_auth_disabled = self._check_mint_authority(token_info)
        if not mint_auth_disabled and self.check_mint_authority:
            risk_flags.append("Mint authority still enabled - inflation risk")
            score -= self.WEIGHTS["mint_authority"]
        
        # Check 2: Freeze Authority
        freeze_auth_disabled = self._check_freeze_authority(token_info)
        if not freeze_auth_disabled and self.check_freeze_authority:
            risk_flags.append("Freeze authority enabled - honeypot risk")
            score -= self.WEIGHTS["freeze_authority"]
        
        # Check 3: Liquidity Lock
        liquidity_locked = self._check_liquidity_lock(pool_info)
        if liquidity_locked is False:
            risk_flags.append("Liquidity not locked - rug pull risk")
            score -= self.WEIGHTS["liquidity_lock"]
        elif liquidity_locked is True:
            score += 5  # Bonus for locked liquidity
        
        # Check 4: Holder Analysis
        holder_analysis = await self._analyze_holders(token_address)
        total_holders = holder_analysis.get("total_holders", 0)
        top_holder_pct = holder_analysis.get("top_holder_percent", 100.0)
        top_10_pct = holder_analysis.get("top_10_holders_percent", 100.0)
        
        if total_holders < self.min_holders:
            risk_flags.append(f"Too few holders ({total_holders} < {self.min_holders})")
            score -= 10
        
        if top_holder_pct > self.max_top_holder_percent:
            risk_flags.append(
                f"Top holder owns {top_holder_pct:.1f}% - whale manipulation risk"
            )
            score -= self.WEIGHTS["top_holder_percent"]
        
        if top_10_pct > 70:
            risk_flags.append(
                f"Top 10 holders own {top_10_pct:.1f}% - concentrated ownership"
            )
            score -= 10
        
        # Check 5: Ownership Renouncement
        renounced = self._check_renounced_ownership(token_info)
        if renounced:
            score += self.WEIGHTS["renounced_ownership"]
        elif renounced is False:
            risk_flags.append("Ownership not renounced")
            score -= 5
        
        # Check 6: Additional heuristics
        additional_risks = self._check_additional_heuristics(pool_info, token_info)
        risk_flags.extend(additional_risks)
        score -= len(additional_risks) * 5
        
        # Ensure score stays in valid range
        score = max(0.0, min(100.0, score))
        
        # Determine if token is safe (threshold: 60/100)
        is_safe = score >= 60.0 and len(risk_flags) <= 2
        
        return TokenSafetyResult(
            is_safe=is_safe,
            score=score,
            mint_authority_disabled=mint_auth_disabled,
            freeze_authority_disabled=freeze_auth_disabled,
            liquidity_locked=liquidity_locked,
            renounced_ownership=renounced,
            total_holders=total_holders,
            top_holder_percent=top_holder_pct,
            top_10_holders_percent=top_10_pct,
            risk_flags=risk_flags,
            metadata={
                "pool_info": pool_info,
                "analysis_timestamp": pool_info.get("timestamp"),
            }
        )
    
    def _check_mint_authority(self, token_info: Dict[str, Any]) -> bool:
        """Check if mint authority is disabled."""
        # In production, this would query the actual token metadata
        # For now, we check if the info is available
        return token_info.get("mint_authority_disabled", False)
    
    def _check_freeze_authority(self, token_info: Dict[str, Any]) -> bool:
        """Check if freeze authority is disabled."""
        return token_info.get("freeze_authority_disabled", False)
    
    def _check_liquidity_lock(self, pool_info: Dict[str, Any]) -> Optional[bool]:
        """
        Check if pool liquidity is locked.
        
        Returns:
            True if locked, False if not locked, None if unknown
        """
        # In production, this would check known lock providers:
        # - StreamFlow
        # - Squad Labs
        # - Unicrypt
        # - Team Finance
        
        return pool_info.get("liquidity_locked")
    
    def _check_renounced_ownership(self, token_info: Dict[str, Any]) -> Optional[bool]:
        """Check if contract ownership has been renounced."""
        return token_info.get("ownership_renounced")
    
    async def _analyze_holders(
        self, 
        token_address: str
    ) -> Dict[str, Any]:
        """
        Analyze token holder distribution for concentration risk.
        
        In production, this would:
        1. Query Solana RPC for all token accounts (getProgramAccounts)
        2. Aggregate balances by owner address
        3. Calculate concentration metrics (top 1, top 10, Gini coefficient)
        4. Check for suspicious patterns (multiple wallets same owner)
        
        Args:
            token_address: Token mint address to analyze
            
        Returns:
            Dictionary with holder analysis metrics
        """
        # Placeholder - implement with actual RPC calls in production
        # Example implementation structure:
        #
        # from solana.rpc.async_api import AsyncClient
        # from solders.pubkey import Pubkey
        #
        # client = AsyncClient(self.rpc_url)
        # token_program = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        # mint_pubkey = Pubkey.from_string(token_address)
        #
        # # Fetch all token accounts for this mint
        # response = await client.get_program_accounts(
        #     token_program,
        #     filters=[
        #         {"dataSize": 165},  # Token account size
        #         {"memcmp": {"offset": 0, "bytes": str(mint_pubkey)}}
        #     ]
        # )
        #
        # # Aggregate by owner and calculate metrics
        # holder_balances = {}
        # for account in response.value:
        #     # Parse account data to extract owner and balance
        #     ...
        #
        # # Calculate concentration metrics
        # total_supply = sum(holder_balances.values())
        # sorted_balances = sorted(holder_balances.values(), reverse=True)
        #
        # top_holder_percent = (sorted_balances[0] / total_supply * 100) if sorted_balances else 0
        # top_10_percent = (sum(sorted_balances[:10]) / total_supply * 100) if len(sorted_balances) >= 10 else 100
        #
        # return {
        #     "total_holders": len(holder_balances),
        #     "top_holder_percent": top_holder_percent,
        #     "top_10_holders_percent": top_10_percent,
        # }
        
        logger.debug(f"Analyzing holders for token {token_address[:8]}...")
        
        return {
            "total_holders": 0,
            "top_holder_percent": 100.0,
            "top_10_holders_percent": 100.0,
        }
    
    def _check_additional_heuristics(
        self,
        pool_info: Dict[str, Any],
        token_info: Dict[str, Any],
    ) -> List[str]:
        """
        Additional heuristic checks for common red flags.
        
        Checks:
        - Extremely high initial liquidity (potential dump)
        - Suspicious token name/symbol
        - Very low decimal places (unusual)
        - Creator wallet history
        """
        risks = []
        
        # Check initial liquidity
        initial_liq = pool_info.get("initial_liquidity_sol", 0)
        if initial_liq > 10000:
            risks.append("Unusually high initial liquidity")
        elif initial_liq < 100:
            risks.append("Very low initial liquidity - high volatility risk")
        
        # Check token metadata
        name = token_info.get("name", "")
        if len(name) > 50:
            risks.append("Suspiciously long token name")
        
        # Check decimals
        decimals = token_info.get("decimals", 9)
        if decimals < 6 or decimals > 18:
            risks.append(f"Unusual decimal count: {decimals}")
        
        return risks
    
    def get_safety_recommendation(self, result: TokenSafetyResult) -> str:
        """
        Get a trading recommendation based on safety analysis.
        
        Args:
            result: TokenSafetyResult from analyze_token()
            
        Returns:
            Recommendation string
        """
        if result.is_safe:
            if result.score >= 80:
                return "✅ STRONG BUY - Excellent safety profile"
            elif result.score >= 70:
                return "✅ BUY - Good safety profile"
            else:
                return "⚠️ PROCEED WITH CAUTION - Moderate risk"
        else:
            if result.score >= 40:
                return "❌ AVOID - High risk detected"
            else:
                return "🚫 DANGEROUS - Multiple critical risks"
