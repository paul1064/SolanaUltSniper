# 🎯 Solana Token Sniper Bot

Ein hochentwickelter, automatisierter Solana-Token-Sniper-Bot mit enterprise-grade Sicherheitsfeatures und optimierter Ausführungsgeschwindigkeit. Der Bot erkennt neu gestartete Token und Liquiditätserweiterungen auf der Solana-Blockchain in Echtzeit und führt blitzschnelle Käufe durch.

## ⚡ Herausragende Features

### 🔐 Enterprise-Grade Sicherheit
- **Multi-Layer Security Filter**: 6-stufige Sicherheitsprüfung vor jedem Trade
- **Private Key Protection**: Keys werden ausschließlich über Umgebungsvariablen geladen
- **Anti-Rug Pull Schutz**: Automatische Erkennung von Mint/Freeze Authority Risiken
- **Whale-Alert System**: Erkennt konzentrierte Token-Holdings (>30% bei einem Holder)
- **Blacklist Integration**: Bekannte Scam-Adressen werden automatisch blockiert

### 🚀 Hochgeschwindigkeits-Ausführung
- **WebSocket Real-Time Monitoring**: Sub-Sekunden Erkennung neuer Pools
- **Optimierte Transaktionsstruktur**: Compute Budget Optimization für schnellere Execution
- **Dynamic Priority Fees**: Automatische Anpassung der Netzwerkgebühren basierend auf Auslastung
- **Jito Bundle Support**: MEV-Protection durch private Transaction Routing (optional)
- **Retry-Logic mit Backoff**: Intelligente Wiederholung fehlgeschlagener Transaktionen

### 🧠 Intelligente Trading-Strategien
1. **Smart Entry Strategy**
   - Dynamische Kaufgrößen basierend auf Pool-Liquidität
   - Staggered Entry (mehrere kleine Käufe statt einem großen)
   - Volatilitäts-basierte Slippage-Anpassung
   
2. **Automated Risk Management**
   - Take-Profit Levels (mehrstufig: 50%, 100%, 200%)
   - Stop-Loss Mechanismen (-25%, -50%)
   - Maximalverlust pro Token (configurable)
   - Daily Loss Limit zum Schutz vor Verlustserien
   - Position Sizing Limits
   
3. **Advanced Pool Detection**
   - Raydium AMM V4 Integration
   - Orca Whirlpool Unterstützung
   - Pump.fun Early Detection
   - Multi-DEX Monitoring parallel

### 📊 Umfangreiches Monitoring
- **Echtzeit-Portfolio-Tracking**: Alle Positionen live im Blick
- **PnL-Analyse**: Gewinn/Verlust je Trade und gesamt
- **Win-Rate Statistics**: Erfolgsquote aller Trades
- **Performance Dashboard**: Detaillierte Statistiken im Log

---

## 📁 Projektstruktur

```
solana_sniper_bot/
├── bot/
│   ├── __init__.py
│   ├── sniper.py              # Haupt-Sniper-Logik & Workflow-Orchestrierung
│   ├── pool_monitor.py        # WebSocket-basierte Pool-Überwachung
│   ├── filters.py             # Schnelle Vorab-Filterung (Liquidity, Blacklists)
│   ├── executor.py            # Transaktionsausführung mit Compute-Optimierung
│   └── risk_manager.py        # Positionsmanagement & Risiko-Kontrolle
├── config/
│   ├── __init__.py
│   └── settings.py            # Pydantic-basierte Konfiguration
├── utils/
│   ├── __init__.py
│   ├── security.py            # Deep Security Analysis (Holder, Authorities)
│   └── helpers.py             # Hilfsfunktionen
├── .env.example               # Umgebungsvariablen Vorlage
├── requirements.txt           # Python-Abhängigkeiten
├── main.py                    # Einstiegspunkt mit CLI
└── README.md                  # Diese Dokumentation
```

---

## 🚀 Installation

### 1. Repository klonen
```bash
git clone <repository-url>
cd solana_sniper_bot
```

### 2. Virtuelle Umgebung erstellen (empfohlen)
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4. Umgebungsvariablen konfigurieren

**WICHTIG**: Private Keys NIEMALS hardcoded speichern!

```bash
cp .env.example .env
nano .env  # Bearbeite mit deinen Werten
```

---

## ⚙️ Konfiguration

### Kritische Umgebungsvariablen

#### 🔑 Wallet Setup (SICHERHEIT!)
```bash
# ✅ RICHTIG: Als Umgebungsvariable
export WALLET_PRIVATE_KEY="dein_base58_key"

# ✅ AUCH RICHTIG: In .env Datei (niemals committen!)
WALLET_PRIVATE_KEY=dein_private_key_hier

# ❌ FALSCH: Hardcoded im Code!
```

**Security Best Practices:**
- Verwende eine separate Trading-Wallet mit limitiertem Kapital
- Speichere den Private Key NIEMALS im Code oder Version Control
- Nutze `.env` Dateien nur lokal und füge sie `.gitignore` hinzu
- In Production: Verwende Secrets Management (AWS Secrets Manager, etc.)

#### 🌐 RPC Endpoints
```env
# Öffentliche Endpoints (rate-limited, nur für Tests)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_WS_URL=wss://api.mainnet-beta.solana.com

# ✅ Empfohlen für Production: Premium RPC Provider
QUICKNODE_URL=https://your-endpoint.quiknode.pro/your-key
HELIUS_URL=https://mainnet.helius-rpc.com/?api-key=your-key
TRITON_URL=https://your-triton.rpcpool.com/your-key
```

#### 💰 Trading Parameter
```env
BUY_AMOUNT_SOL=0.1
MAX_SLIPPAGE_BPS=500
PRIORITY_FEE_LAMPORTS=100000
```

#### 🛡️ Sicherheitslimits
```env
MIN_LIQUIDITY_SOL=1000
MAX_LIQUIDITY_SOL=100000
MAX_LOSS_PER_TOKEN_SOL=0.05
DAILY_LOSS_LIMIT_SOL=1.0
```

#### 🔍 Token Safety Checks
```env
CHECK_MINT_AUTHORITY=true
CHECK_FREEZE_AUTHORITY=true
MIN_HOLDERS=10
MAX_TOP_HOLDER_PERCENT=30
```

#### ⚡ Advanced Features
```env
ENABLE_JITO=false
JITO_AUTH_KEYPAIR=
ENABLE_AUTO_SELL=true
TAKE_PROFIT_PERCENT=100
STOP_LOSS_PERCENT=50
```

#### 🤖 Bot Einstellungen
```env
DRY_RUN=true
LOG_LEVEL=INFO
```

---

## 🎯 Verwendung

### Standard-Start (Dry Run Mode - sicher!)
```bash
python main.py
```

### Mit benutzerdefinierten Parametern
```bash
python main.py --buy-amount 0.5 --min-liquidity 5000 --log-level DEBUG
```

### Production Mode (⚠️ ECHTE TRADES!)
```bash
export WALLET_PRIVATE_KEY="your_key"
python main.py --dry-run false
```

### CLI Optionen Übersicht
```bash
python main.py --help

Optionen:
  --dry-run TEXT          Simulation mode (default: True)
  --buy-amount FLOAT      SOL Betrag pro Trade
  --min-liquidity FLOAT   Minimale Pool-Liquidität in SOL
  --log-level TEXT        Logging Level (DEBUG/INFO/WARNING/ERROR)
  --version               Versionsinformation
```

---

## 🛡️ Sicherheitshinweise

### Private Key Security - DAS IST KRITISCH!

⚠️ **NIEMALS** den Private Key hardcoded in Dateien speichern!

✅ **RICHTIG**: Als Umgebungsvariable
```bash
export WALLET_PRIVATE_KEY="dein_key_hier"
python main.py
```

✅ **RICHTIG**: In .env Datei (nicht committen!)
```env
WALLET_PRIVATE_KEY=dein_key_hier
```

✅ **BESTE PRACTICE**: Secrets Management in Production
```bash
# AWS Secrets Manager
WALLET_PRIVATE_KEY=$(aws secretsmanager get-secret-value ...)

# HashiCorp Vault
WALLET_PRIVATE_KEY=$(vault kv get -field=key secret/sniper-bot)
```

### Wallet Best Practices
1. **Separate Trading Wallet**: Verwende NIE deine Hauptwallet!
2. **Limitiertes Kapital**: Nur so viel wie du verlieren kannst
3. **Testnet First**: Teste ausgiebig im Devnet/Testnet
4. **Continuous Monitoring**: Überwache den Bot aktiv
5. **Software Updates**: Halte alle Dependencies aktuell

---

## ⚠️ Risikowarnung

**Trading von neu gelisteten Token ist EXTREM riskant!**

| Risiko | Beschreibung |
|--------|--------------|
| 🔴 **Scams/Rug Pulls** | 90%+ neuer Token sind betrügerisch |
| 🔴 **Totalverlust** | Hohe Volatilität kann zum kompletten Verlust führen |
| 🔴 **Technische Fehler** | Bugs können unerwartete Verluste verursachen |
| 🔴 **Netzwerk-Probleme** | Überlastung führt zu failed Transactions |
| 🔴 **MEV/Front-Running** | Andere Bots können deine Trades front-runnen |

**Goldene Regel**: Verwende NUR Kapital, dessen vollständigen Verlust du verkraften kannst!

---

## 📊 Beispiel Log Output

```
╔═══════════════════════════════════════════════════════════╗
║           🎯 SOLANA TOKEN SNIPER BOT 🎯                   ║
║   High-speed automated trading for new Solana tokens      ║
║   ⚠️  USE AT YOUR OWN RISK - CRYPTO TRADING IS DANGEROUS  ║
╚═══════════════════════════════════════════════════════════╝

[2024-01-15 10:30:45] INFO: Configuration:
[2024-01-15 10:30:45] INFO:   Mode: DRY RUN
[2024-01-15 10:30:45] INFO:   Buy Amount: 0.1 SOL
[2024-01-15 10:30:45] INFO:   Min Liquidity: 1000 SOL

[2024-01-15 10:31:22] INFO: Starting PoolMonitor...
[2024-01-15 10:31:23] INFO: Subscribed to raydium (subscription ID: 12345)

[2024-01-15 10:32:15] INFO: 🆕 New pool detected on raydium! | Token: 7xG...abc
[2024-01-15 10:32:16] INFO: 🔍 Analyzing new pool: 7xG...abc | Liquidity: 2500 SOL
[2024-01-15 10:32:17] INFO: ✅ Token passed initial filters
[2024-01-15 10:32:18] INFO: ✅ Security check passed: Score: 85.0/100
[2024-01-15 10:32:19] INFO: Executing BUY: 0.1 SOL -> 7xG...abc
[2024-01-15 10:32:20] INFO: [DRY RUN] Simulating buy order...
[2024-01-15 10:32:20] INFO: ✅ BUY EXECUTED! TX: DRY_RUN_7xG...abc
```

---

## 🔧 Erweiterte Funktionen

### Jito Bundle Integration (MEV Protection)
```env
ENABLE_JITO=true
JITO_AUTH_KEYPAIR=dein_jito_auth_key
```

### Custom Filter erstellen
```python
class MyCustomFilter(TokenFilter):
    async def filter_token(self, token_address, pool_address, pool_info):
        if not self._my_custom_check(pool_info):
            return FilterResult(passed=False, rejection_reason="Custom check failed")
        return await super().filter_token(token_address, pool_address, pool_info)
```

---

## 📈 Performance-Optimierung

### Empfohlene Infrastructure

| Komponente | Empfehlung | Warum |
|------------|-----------|-------|
| RPC Provider | QuickNode/Helius/Triton | Niedrige Latenz |
| Server Location | AWS us-west-2 | Nahe an Validatoren |
| Netzwerk | Dedicated Server | <50ms Latenz |
| RAM | Minimum 4GB | Parallele Connections |

### Benchmark Targets

| Metrik | Target |
|--------|--------|
| Pool Detection Time | <500ms |
| Filter Execution | <100ms |
| Security Check | <2s |
| Trade Execution | <5s |

---

## 🧪 Testing

```bash
# Dry Run Mode (empfohlen!)
python main.py --dry-run true

# Mit Devnet testen
export SOLANA_RPC_URL=https://api.devnet.solana.com
python main.py --dry-run true
```

---

## 🐛 Troubleshooting

**Problem**: "WALLET_PRIVATE_KEY must be set"
```bash
export WALLET_PRIVATE_KEY="your_key"
```

**Problem**: "Transaction failed: Blockhash not found"
```bash
# Priority Fee erhöhen
PRIORITY_FEE_LAMPORTS=200000
```

---

## 🤝 Contributing

1. Fork das Repository
2. Feature Branch erstellen (`git checkout -b feature/amazing-feature`)
3. Commits machen (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing-feature`)
5. Pull Request öffnen

---

## 📄 Lizenz

MIT License

---

## 🙏 Disclaimer

**WICHTIG**: Dieser Bot dient ausschließlich Bildungs- und Forschungszwecken.

- ⚠️ Crypto-Trading birgt erhebliche finanzielle Risiken
- ⚠️ Die Entwickler haften nicht für Verluste
- ⚠️ Nutzung erfolgt auf eigene Gefahr

**Empfehlung**: Starte mit kleinen Beträgen und teste ausgiebig im Dry-Run Mode!

---

## 📚 Ressourcen

- [Solana Documentation](https://docs.solana.com/)
- [Raydium SDK](https://github.com/raydium-io/raydium-sdk)
- [Jito MEV](https://docs.jito.wtf/)
- [Helius RPC](https://www.helius.dev/)

---

**Viel Erfolg beim Snipen! 🚀🎯**

*Denke immer: DYOR - Do Your Own Research!*
