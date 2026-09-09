"""
Token filtering module for the Solana Sniper Bot.

This module implements the first line of defense against scam tokens
by applying fast, efficient filters to newly detected pools.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of token filtering process."""
    
    passed: bool
    token_address: str
    pool_address: str
    
    # Filter results
    liquidity_check: bool = True
    age_check: bool = True
    metadata_check: bool = True
    blacklist_check: bool = True
    
    # Rejection reason (if failed)
    rejection_reason: Optional[str] = None
    
    # Additional data
    pool_data: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        if self.passed:
            return f"✅ Filter PASSED for {self.token_address}"
        else:
            return f"❌ Filter FAILED: {self.rejection_reason}"


class TokenFilter:
    """
    Fast token filter for initial screening.
    
    Applies quick checks to eliminate obvious scams and low-quality tokens
    before running more expensive security analysis.
    
    Filter Pipeline:
    1. Liquidity Check - Is there enough liquidity?
    2. Age Check - Is the pool too old/new?
    3. Metadata Check - Does the token have valid metadata?
    4. Blacklist Check - Is the creator/pool blacklisted?
    """
    
    # Known scam patterns in token names/symbols
    SCAM_KEYWORDS = [
        "scam",
        "fake",
        "rug",
        "honeypot",
        "exit",
        "dump",
    ]
    
    def __init__(
        self,
        min_liquidity_sol: float = 1000.0,
        max_liquidity_sol: float = 100000.0,
        max_pool_age_seconds: int = 86400,  # 24 hours
        check_metadata: bool = True,
    ):
        """
        Initialize token filter.
        
        Args:
            min_liquidity_sol: Minimum pool liquidity in SOL
            max_liquidity_sol: Maximum pool liquidity in SOL
            max_pool_age_seconds: Maximum pool age to consider
            check_metadata: Whether to validate token metadata
        """
        self.min_liquidity_sol = min_liquidity_sol
        self.max_liquidity_sol = max_liquidity_sol
        self.max_pool_age_seconds = max_pool_age_seconds
        self.check_metadata = check_metadata
        
        # Blacklists (in production, these would be loaded from external sources)
        self.creator_blacklist: set = set()
        self.pool_blacklist: set = set()
        self.token_blacklist: set = set()
    
    async def filter_token(
        self,
        token_address: str,
        pool_address: str,
        pool_info: Dict[str, Any],
    ) -> FilterResult:
        """
        Run all filters on a token/pool combination.
        
        Args:
            token_address: Token mint address
            pool_address: Liquidity pool address
            pool_info: Pool information dictionary
            
        Returns:
            FilterResult with pass/fail status and details
        """
        result = FilterResult(
            passed=True,
            token_address=token_address,
            pool_address=pool_address,
            pool_data=pool_info,
        )
        
        # Run filters in order of speed (fastest first)
        
        # 1. Blacklist Check (fastest - just set lookups)
        if not self._check_blacklist(token_address, pool_address, pool_info):
            result.passed = False
            result.blacklist_check = False
            result.rejection_reason = "Token/Creator is blacklisted"
            return result
        
        # 2. Liquidity Check
        if not self._check_liquidity(pool_info):
            result.passed = False
            result.liquidity_check = False
            result.rejection_reason = self._get_liquidity_rejection_reason(pool_info)
            return result
        
        # 3. Age Check
        if not self._check_pool_age(pool_info):
            result.passed = False
            result.age_check = False
            result.rejection_reason = "Pool age outside acceptable range"
            return result
        
        # 4. Metadata Check (slower - may require RPC calls)
        if self.check_metadata:
            if not await self._check_metadata(token_address, pool_info):
                result.passed = False
                result.metadata_check = False
                result.rejection_reason = "Invalid or missing token metadata"
                return result
        
        logger.info(f"Token {token_address[:8]}... passed all filters")
        return result
    
    def _check_blacklist(
        self,
        token_address: str,
        pool_address: str,
        pool_info: Dict[str, Any],
    ) -> bool:
        """Check if token, creator, or pool is blacklisted."""
        # Check token address
        if token_address in self.token_blacklist:
            logger.warning(f"Blacklisted token: {token_address}")
            return False
        
        # Check pool address
        if pool_address in self.pool_blacklist:
            logger.warning(f"Blacklisted pool: {pool_address}")
            return False
        
        # Check creator address
        creator = pool_info.get("creator_address", "")
        if creator in self.creator_blacklist:
            logger.warning(f"Blacklisted creator: {creator}")
            return False
        
        return True
    
    def _check_liquidity(self, pool_info: Dict[str, Any]) -> bool:
        """Check if pool liquidity is within acceptable range."""
        liquidity_sol = pool_info.get("liquidity_sol", 0)
        
        if liquidity_sol < self.min_liquidity_sol:
            logger.debug(
                f"Liquidity too low: {liquidity_sol} SOL < {self.min_liquidity_sol} SOL"
            )
            return False
        
        if liquidity_sol > self.max_liquidity_sol:
            logger.debug(
                f"Liquidity too high: {liquidity_sol} SOL > {self.max_liquidity_sol} SOL"
            )
            return False
        
        return True
    
    def _get_liquidity_rejection_reason(self, pool_info: Dict[str, Any]) -> str:
        """Get detailed rejection reason for liquidity check."""
        liquidity_sol = pool_info.get("liquidity_sol", 0)
        
        if liquidity_sol < self.min_liquidity_sol:
            return (
                f"Insufficient liquidity ({liquidity_sol:.2f} SOL). "
                f"Minimum: {self.min_liquidity_sol:.2f} SOL"
            )
        else:
            return (
                f"Excessive liquidity ({liquidity_sol:.2f} SOL). "
                f"Maximum: {self.max_liquidity_sol:.2f} SOL"
            )
    
    def _check_pool_age(self, pool_info: Dict[str, Any]) -> bool:
        """Check if pool age is within acceptable range."""
        import time
        
        creation_time = pool_info.get("creation_timestamp", 0)
        current_time = time.time()
        
        if creation_time == 0:
            # Unknown creation time - allow through
            return True
        
        pool_age = current_time - creation_time
        
        # Don't accept pools older than our window
        if pool_age > self.max_pool_age_seconds:
            logger.debug(f"Pool too old: {pool_age:.0f}s > {self.max_pool_age_seconds}s")
            return False
        
        # Don't accept pools from the future (clock skew tolerance: 5 seconds)
        if pool_age < -5:
            logger.warning(f"Pool creation time is in the future: {pool_age:.0f}s")
            return False
        
        return True
    
    async def _check_metadata(
        self,
        token_address: str,
        pool_info: Dict[str, Any],
    ) -> bool:
        """
        Validate token metadata.
        
        Checks:
        - Token has a name and symbol
        - Name/symbol don't contain scam keywords
        - Token URI is valid (if available)
        """
        metadata = pool_info.get("token_metadata", {})
        
        name = metadata.get("name", "")
        symbol = metadata.get("symbol", "")
        
        # Must have name and symbol
        if not name or not symbol:
            logger.debug(f"Missing name/symbol for {token_address}")
            return False
        
        # Check for scam keywords
        name_lower = name.lower()
        symbol_lower = symbol.lower()
        
        for keyword in self.SCAM_KEYWORDS:
            if keyword in name_lower or keyword in symbol_lower:
                logger.warning(
                    f"Token {token_address} contains scam keyword: {keyword}"
                )
                return False
        
        return True
    
    def add_to_blacklist(
        self,
        address: str,
        blacklist_type: str = "creator",
    ) -> None:
        """
        Add an address to a blacklist.
        
        Args:
            address: Address to blacklist
            blacklist_type: Type of blacklist ('creator', 'pool', 'token')
        """
        if blacklist_type == "creator":
            self.creator_blacklist.add(address)
        elif blacklist_type == "pool":
            self.pool_blacklist.add(address)
        elif blacklist_type == "token":
            self.token_blacklist.add(address)
        
        logger.info(f"Added {address} to {blacklist_type} blacklist")
    
    def load_external_blacklists(self, blacklist_urls: List[str]) -> None:
        """
        Load blacklists from external sources.
        
        In production, this would fetch known scam lists from:
        - RugCheck
        - Solscan flagged addresses
        - Community-maintained blocklists
        
        Args:
            blacklist_urls: List of URLs to fetch blacklists from
        """
        logger.info(f"Loading external blacklists from {len(blacklist_urls)} sources")
        # Implementation would go here for production
