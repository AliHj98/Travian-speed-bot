#!/usr/bin/env python3
"""
Travian AI Assistant Bot
Self-healing bot that uses Claude AI to fix its own issues
With comprehensive logging
"""

import sys
import time
import signal
from datetime import datetime

from config import config
from core.browser import BrowserManager
from core.session import TravianSession
from modules.resources import ResourceMonitor
from modules.buildings import BuildingManager
from modules.military import MilitaryManager
from modules.ai_strategy import AIStrategist
from modules.self_heal import SelfHealingBot, SmartElementFinder
from utils.helpers import Logger, ActionLogger, format_time


class TravianBot:
    """Main bot controller with self-healing capabilities and logging"""

    def __init__(self):
        self.browser = None
        self.session = None
        self.resources = None
        self.buildings = None
        self.military = None
        self.ai = None
        self.healer = None
        self.smart_finder = None
        self.running = False
        self.cycle_count = 0

        # Initialize action logger
        self.action_log = ActionLogger()

    def initialize(self) -> bool:
        """Initialize all bot components"""
        Logger.log_separator("INITIALIZATION")
        Logger.info("Initializing Travian AI Assistant...")

        # Validate configuration
        if not config.validate_credentials():
            Logger.error("Missing credentials! Please set TRAVIAN_USERNAME and TRAVIAN_PASSWORD in .env file")
            return False

        try:
            # Initialize browser
            self.browser = BrowserManager()
            self.browser.start()
            Logger.success("Browser started")

            # Initialize self-healing AI
            self.healer = SelfHealingBot(self.browser)
            self.smart_finder = SmartElementFinder(self.browser, self.healer)

            if self.healer.is_available():
                Logger.success("Self-healing AI initialized")
            else:
                Logger.warning("Self-healing AI not available (no API key)")

            # Initialize session
            self.session = TravianSession(self.browser)

            # Initialize modules
            self.resources = ResourceMonitor(self.browser)
            self.resources.healer = self.healer
            self.resources.smart_finder = self.smart_finder

            self.buildings = BuildingManager(self.browser, self.resources)
            self.military = MilitaryManager(self.browser, self.resources)
            self.ai = AIStrategist()

            Logger.success("All components initialized")
            Logger.log_separator()
            return True

        except Exception as e:
            Logger.error(f"Initialization failed: {e}")
            self.action_log.log_error("initialization", str(e))
            return False

    def login(self) -> bool:
        """Login to Travian"""
        try:
            Logger.info(f"Logging in as {config.username}...")
            result = self.session.login()
            self.action_log.log_login(config.username, result)

            if result:
                Logger.success("Login successful")
            else:
                Logger.error("Login failed")

            return result
        except Exception as e:
            Logger.error(f"Login failed: {e}")
            self.action_log.log_login(config.username, False)
            self.action_log.log_error("login", str(e))
            return False

    def run_cycle(self):
        """Run one cycle of bot operations"""
        self.cycle_count += 1
        actions_taken = []

        Logger.log_separator(f"CYCLE #{self.cycle_count}")
        Logger.info(f"Starting cycle #{self.cycle_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Update game state
            self.update_game_state()
            actions_taken.append("status_update")

            # Log resources
            self.action_log.log_resources(
                self.resources.resources,
                self.resources.production
            )

            # Get AI recommendations
            game_data = self.collect_game_data()

            # Use AI strategist for advice
            if self.healer and self.healer.is_available():
                Logger.ai("Getting strategic advice...")
                strategy = self.healer.get_game_strategy(game_data)
                if strategy:
                    Logger.info(f"AI Strategy: {strategy[:200]}...")

            next_action = self.ai.get_next_action(game_data)
            if next_action:
                Logger.info(f"Recommended action: {next_action}")

            # Execute automated tasks
            if config.auto_build and not self.buildings.is_queue_full():
                Logger.action("Running auto-upgrade...")
                result = self.execute_with_healing("auto_build", self.buildings.auto_upgrade_resources, self.session)
                if result:
                    actions_taken.append("upgrade")

            if config.auto_train_troops:
                Logger.action("Running auto-train...")
                result = self.execute_with_healing("auto_train", self.military.auto_train_troops)
                if result:
                    actions_taken.append("train")

            # Check for threats
            incoming = self.military.check_incoming_attacks()
            if incoming:
                Logger.warning(f"{len(incoming)} incoming attack(s) detected!")
                for attack in incoming:
                    self.action_log.log_incoming_attack(
                        attack.get('attacker', 'Unknown'),
                        attack.get('arrival_time', 'Unknown')
                    )
                actions_taken.append("attack_detected")

            # Log cycle completion
            self.action_log.log_cycle(self.cycle_count, actions_taken)
            Logger.success(f"Cycle #{self.cycle_count} completed")

        except Exception as e:
            Logger.error(f"Error in cycle: {e}")
            self.action_log.log_error(f"cycle_{self.cycle_count}", str(e))
            self.handle_error(e)

    def execute_with_healing(self, action_name: str, func, *args, **kwargs):
        """Execute a function with self-healing on error"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            Logger.warning(f"Action '{action_name}' failed: {e}")
            self.action_log.log_error(action_name, str(e))

            if self.healer.is_available():
                Logger.ai("Attempting self-heal...")
                self.browser.screenshot(f'error_{action_name}.png')

                result = self.healer.debug_and_fix(
                    error_description=str(e),
                    current_code=f"Function: {func.__name__}",
                    page_html=self.browser.get_page_source()[:20000]
                )

                if result:
                    Logger.ai(f"AI Analysis: {result.get('explanation', 'No explanation')}")

            return None

    def handle_error(self, error: Exception):
        """Handle errors with AI assistance"""
        self.browser.screenshot(f'error_cycle_{self.cycle_count}.png')

        if self.healer and self.healer.is_available():
            Logger.ai("Analyzing error with AI...")
            analysis = self.healer.analyze_screenshot(
                f'screenshots/error_cycle_{self.cycle_count}.png',
                f"An error occurred: {error}. What's visible on the screen that might explain this?"
            )
            if analysis:
                Logger.ai(f"Error analysis: {analysis[:300]}...")

    def update_game_state(self):
        """Update current game state - FAST"""
        try:
            self.session.navigate_to_village_overview()
            # No sleep needed - browser waits for page load

            self.resources.update_resources()
            self.resources.update_production()

            village = self.session.get_current_village()
            Logger.info(f"Village: {village}")
            Logger.resource(f"Resources: {self.resources.format_resources()}")

        except Exception as e:
            Logger.error(f"Error updating game state: {e}")
            self.action_log.log_error("update_state", str(e))
            self.handle_error(e)

    def collect_game_data(self) -> dict:
        """Collect all game data for AI analysis"""
        return {
            'resources': self.resources.resources.copy(),
            'production': self.resources.production.copy(),
            'storage_capacity': self.resources.storage_capacity.copy(),
            'buildings': [],
            'troops': self.military.troops.copy(),
            'cycle': self.cycle_count,
            'server_speed': '10000x'
        }

    def main_loop(self):
        """Main bot loop"""
        Logger.log_separator("MAIN LOOP STARTED")
        Logger.info(f"Check interval: {format_time(config.check_interval)}")
        Logger.info(f"Auto build: {'ON' if config.auto_build else 'OFF'}")
        Logger.info(f"Auto train: {'ON' if config.auto_train_troops else 'OFF'}")
        Logger.info(f"Self-healing: {'ON' if self.healer and self.healer.is_available() else 'OFF'}")

        self.running = True

        while self.running:
            try:
                self.run_cycle()

                Logger.info(f"Sleeping for {format_time(config.check_interval)}...")
                for i in range(config.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                Logger.info("Received interrupt signal")
                self.stop()
                break
            except Exception as e:
                Logger.error(f"Unexpected error in main loop: {e}")
                self.action_log.log_error("main_loop", str(e))
                self.handle_error(e)
                time.sleep(10)

    def stop(self):
        """Stop the bot gracefully"""
        Logger.log_separator("SHUTDOWN")
        Logger.info("Stopping bot...")
        self.running = False

        if self.session:
            self.session.logout()

        if self.browser:
            self.browser.stop()

        Logger.success("Bot stopped successfully")
        Logger.info(f"Total cycles completed: {self.cycle_count}")

    def run(self):
        """Main entry point"""
        print("=" * 60)
        print("🤖 TRAVIAN AI ASSISTANT (Self-Healing Edition)")
        print("=" * 60)
        print(f"Server: {config.server}")
        print(f"Username: {config.username}")
        print(f"Auto Build: {'ON' if config.auto_build else 'OFF'}")
        print(f"Auto Train: {'ON' if config.auto_train_troops else 'OFF'}")
        print(f"Logs: logs/")
        print("=" * 60)
        print()

        Logger.log_separator("BOT STARTED")
        Logger.info(f"Travian AI Assistant starting...")
        Logger.info(f"Server: {config.server}")
        Logger.info(f"Username: {config.username}")

        # Initialize
        if not self.initialize():
            Logger.error("Failed to initialize bot")
            return 1

        Logger.info(f"AI Features: {'ENABLED' if self.ai and self.ai.is_available() else 'DISABLED'}")
        Logger.info(f"Self-Healing: {'ENABLED' if self.healer and self.healer.is_available() else 'DISABLED'}")

        # Login
        if not self.login():
            Logger.error("Failed to login")
            self.stop()
            return 1

        # Setup signal handlers
        signal.signal(signal.SIGINT, lambda s, f: self.stop())
        signal.signal(signal.SIGTERM, lambda s, f: self.stop())

        # Start main loop
        try:
            self.main_loop()
        except Exception as e:
            Logger.critical(f"Fatal error: {e}")
            self.action_log.log_error("fatal", str(e))
            self.stop()
            return 1

        return 0


def main():
    """Entry point"""
    bot = TravianBot()
    sys.exit(bot.run())


if __name__ == "__main__":
    main()
