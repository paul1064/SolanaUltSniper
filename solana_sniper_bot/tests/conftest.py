import sys
from pathlib import Path

# The bot uses top-level imports (bot.*, config.*, utils.*) relative to solana_sniper_bot/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
