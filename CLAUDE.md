# CLAUDE.md - Project Documentation for AI Assistants

This file provides context and guidance for Claude (or other AI assistants) working on this codebase.

## Project Overview

**Travian Speed Bot** - A Python-based automation assistant for Travian browser game (specifically ts1.travian-speed.com). Uses Selenium WebDriver (Firefox) for browser automation and integrates with Claude AI for self-healing capabilities and strategic decisions.

## Tech Stack

- **Python 3.13+**
- **Selenium WebDriver** (Firefox/geckodriver)
- **Anthropic Claude API** for AI features
- **Pydantic** for configuration validation
- **python-dotenv** for environment management

## Project Structure

```
travian/
├── bot.py                 # Simple automated bot (runs in loop)
├── interactive_bot.py     # Full interactive menu-driven bot (main entry point)
├── config.py              # Configuration management (BotConfig class)
├── inspect_page.py        # Debug utility to inspect page elements
├── test_connection.py     # Test browser/login connectivity
│
├── core/                  # Core browser and session management
│   ├── browser.py         # BrowserManager - Selenium wrapper, multi-tab support
│   └── session.py         # TravianSession - Login, navigation, captcha handling
│
├── modules/               # Game-specific automation modules
│   ├── resources.py       # ResourceMonitor - Track wood/clay/iron/crop
│   ├── buildings.py       # BuildingManager - Auto-upgrade buildings
│   ├── military.py        # MilitaryManager - Troop training, attacks
│   ├── farming.py         # FarmListManager - Automated raiding
│   ├── village_map.py     # VillageMap - Multi-village management
│   ├── task_queue.py      # TaskExecutor - Queued task execution
│   ├── ai_strategy.py     # AIStrategist - AI-powered game decisions
│   ├── captcha.py         # CaptchaSolver - Claude Vision captcha solving
│   └── self_heal.py       # SelfHealingBot - AI-powered error recovery
│
├── utils/                 # Utility functions
│   └── helpers.py         # Logger, ActionLogger, formatting helpers
│
├── requirements.txt       # Python dependencies
├── setup.sh              # Setup script
└── .env.example          # Environment template
```

## Key Classes

### Core Classes

| Class | File | Purpose |
|-------|------|---------|
| `BrowserManager` | `core/browser.py` | Selenium Firefox wrapper with multi-tab support, element finding, screenshots |
| `TravianSession` | `core/session.py` | Login flow, credential auto-fill, captcha handling, navigation |
| `BotConfig` | `config.py` | Pydantic config loading from .env file |

### Module Classes

| Class | File | Purpose |
|-------|------|---------|
| `ResourceMonitor` | `modules/resources.py` | Tracks resources (wood/clay/iron/crop), production rates, storage |
| `BuildingManager` | `modules/buildings.py` | Auto-upgrade buildings, smart build order, resource fields |
| `MilitaryManager` | `modules/military.py` | Troop training, attack detection, military operations |
| `FarmListManager` | `modules/farming.py` | Farm list management, automated raiding with travel time tracking |
| `VillageMap` | `modules/village_map.py` | Multi-village caching and management |
| `SelfHealingBot` | `modules/self_heal.py` | AI-powered selector recovery and error analysis |
| `CaptchaSolver` | `modules/captcha.py` | Claude Vision-based captcha solving |
| `InteractiveBot` | `interactive_bot.py` | Main menu-driven interface |

## Cache Files

The bot generates several cache/data files that persist between sessions:

| File | Purpose | Safe to Delete |
|------|---------|----------------|
| `farm_list.json` | Farm targets, troop configs, raid history | Yes (loses farm list) |
| `village_cache.json` | Cached village data, building states | Yes (will rescan) |
| `village_training.json` | Troop training queues | Yes |
| `bot_settings.json` | User preferences | Yes (resets to defaults) |
| `session_data/` | Browser session cookies | Yes (requires re-login) |
| `screenshots/` | Debug screenshots | Yes |
| `logs/` | Log files | Yes |

## Common Patterns

### Finding Elements

The bot uses multiple selector strategies with fallbacks:

```python
# Fast find (no wait)
element = self.browser.find_element_fast(By.CSS_SELECTOR, selector)

# With timeout
element = self.browser.find_element(By.ID, 'element_id', timeout=3)

# Multiple selectors with fallback
selectors = [(By.ID, 'id1'), (By.CSS_SELECTOR, '.class1'), ...]
for by, selector in selectors:
    elem = self.browser.find_element(by, selector, timeout=1)
    if elem:
        break
```

### Navigation

```python
from config import config

# Navigate to village overview (resource fields)
self.browser.navigate_to(f"{config.base_url}/dorf1.php")

# Navigate to village center (buildings)
self.browser.navigate_to(f"{config.base_url}/dorf2.php")

# Navigate to specific building by slot ID
self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
```

### Resource IDs in Travian

- `l1` = Wood
- `l2` = Clay
- `l3` = Iron
- `l4` = Crop
- `l5` = Crop consumption / Free crop

### Building Slot IDs

- Slots 1-18: Resource fields (outside village)
- Slots 19-40: Village buildings (inside village)
- Slot 39: Usually Rally Point

### Troop Input Names

Troops use `t1` through `t11` naming:
- `t1`-`t6`: Combat troops (tribe-specific)
- `t7`: Battering Ram
- `t8`: Catapult/Trebuchet
- `t9`: Chief/Senator/Chieftain
- `t10`: Settler
- `t11`: Hero

## Environment Variables

Required in `.env`:

```bash
TRAVIAN_SERVER=ts1.travian-speed.com
TRAVIAN_USERNAME=your_username
TRAVIAN_PASSWORD=your_password
ANTHROPIC_API_KEY=your_api_key  # Optional, for AI features
HEADLESS=false                   # Run browser headlessly
CHECK_INTERVAL=60                # Seconds between auto-mode cycles
AUTO_BUILD=true
AUTO_TRAIN_TROOPS=true
```

## Running the Bot

```bash
# Interactive mode (recommended)
python interactive_bot.py

# Simple automated mode
python bot.py

# Test connection
python test_connection.py

# Debug page elements
python inspect_page.py
```

## Interactive Bot Menu Structure

```
Main Menu
├── 1. Status - View resources, buildings, troops
├── 2. Buildings - Upgrade, scan, auto-upgrade
├── 3. Military - Train troops, send attacks/raids
├── 4. Farming - Manage farm lists, auto-raid
├── 5. AI Assistant - Get strategic advice
├── 6. Auto Mode - Continuous automation
├── 7. Settings - Configure bot behavior
├── 8. Navigation - Manual page navigation
├── 9. Multi-Tab - Manage browser tabs
├── 10. Village Map - Multi-village management
└── 0. Exit
```

## Key Implementation Notes

1. **Speed Optimization**: The bot minimizes `time.sleep()` calls and uses short timeouts for speed servers.

2. **Self-Healing**: When selectors fail, `SelfHealingBot` can analyze the page and suggest new selectors using Claude AI.

3. **Multi-Village**: `VillageMap` caches village data to reduce navigation overhead.

4. **Farm Timing**: `FarmListManager` tracks travel times to re-send raids when troops return.

5. **Error Recovery**: Failed operations navigate back to main page to reset state.

6. **Connection Resilience**: Auto-mode and autopilot automatically wait for connection restoration on network errors using `wait_for_connection()` and `is_connection_error()` helpers.

## Useful Commands for Development

```bash
# Clear all cache files
rm -f farm_list.json village_cache.json village_training.json bot_settings.json
rm -rf session_data/ screenshots/ logs/

# Watch logs
tail -f logs/*.log

# Check what's cached
cat village_cache.json | python -m json.tool
```

## Adding New Features

When adding new automation:

1. Add module in `modules/` following existing patterns
2. Import and initialize in `InteractiveBot.__init__`
3. Add menu option in appropriate `*_menu()` method
4. Use `stop_callback` pattern for interruptible loops
5. Save state to JSON for persistence
6. Handle errors gracefully with navigation reset

## Security Notes

- Never commit `.env` file (contains credentials)
- `farm_list.json` may contain game-specific data
- Screenshots may contain sensitive game state
- The bot respects Travian's ToS warning in README
