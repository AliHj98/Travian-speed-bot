#!/usr/bin/env python3
"""
Travian Interactive AI Assistant
Menu-driven bot with full control and AI assistance
"""

import os
import sys
import time
import json
import re
import select
import termios
import tty
from datetime import datetime
from typing import Optional, Dict, List
from threading import Thread, Event
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from urllib3.exceptions import MaxRetryError, NewConnectionError, ReadTimeoutError
from requests.exceptions import ConnectionError, ReadTimeout

from config import config
from core.browser import BrowserManager
from core.session import TravianSession
from modules.resources import ResourceMonitor
from modules.buildings import BuildingManager
from modules.military import MilitaryManager
from modules.self_heal import SelfHealingBot
from modules.village_map import VillageMap
from modules.village_cycler import VillageCycler
from modules.task_queue import TaskExecutor, TaskQueue, TaskStatus
from modules.farming import FarmListManager
from modules.farm_finder import FarmFinder, ScanFilter
from modules.reports import ReportManager, OUTCOME_LABELS
from utils.helpers import Logger, ActionLogger, setup_logger


class Colors:
    """ANSI color codes for terminal"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


# Connection error types that indicate network issues
CONNECTION_ERRORS = (
    WebDriverException,
    TimeoutException,
    MaxRetryError,
    NewConnectionError,
    ReadTimeoutError,
    ConnectionError,
    ReadTimeout,
    OSError,
)


def is_connection_error(e: Exception) -> bool:
    """Check if exception is a connection-related error"""
    error_msg = str(e).lower()
    connection_keywords = [
        'read timed out',
        'connection refused',
        'connection reset',
        'no route to host',
        'network is unreachable',
        'name or service not known',
        'temporary failure',
        'connectionpool',
        'max retries',
        'newconnectionerror',
        'remotedisconnected',
    ]
    if isinstance(e, CONNECTION_ERRORS):
        return True
    return any(keyword in error_msg for keyword in connection_keywords)


def print_header(title: str):
    """Print a styled header"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.YELLOW}  {title}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_menu(title: str, options: list):
    """Print a menu with numbered options"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}[ {title} ]{Colors.END}\n")
    for i, option in enumerate(options, 1):
        print(f"  {Colors.CYAN}{i}.{Colors.END} {option}")
    print(f"  {Colors.CYAN}0.{Colors.END} Back / Exit")
    print()


def get_input(prompt: str = "> ") -> str:
    """Get user input with colored prompt"""
    try:
        return input(f"{Colors.YELLOW}{prompt}{Colors.END}").strip()
    except (KeyboardInterrupt, EOFError):
        return "0"


class StopFlag:
    """Thread-safe stop flag for loops"""
    def __init__(self):
        self.stop_event = Event()
        self.background_event = Event()

    def stop(self):
        self.stop_event.set()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def send_to_background(self):
        self.background_event.set()

    def is_background(self) -> bool:
        return self.background_event.is_set()

    def reset(self):
        self.stop_event.clear()
        self.background_event.clear()


def check_for_keypress() -> Optional[str]:
    """Non-blocking check for keypress (Linux)"""
    try:
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
    except:
        pass
    return None


def key_listener(stop_flag: StopFlag, stop_keys: list = ['q', 's'], background_key: str = 'b'):
    """Background thread that listens for stop/background keys"""
    old_settings = None
    try:
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

        while not stop_flag.should_stop() and not stop_flag.is_background():
            if select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.read(1).lower()
                if key in stop_keys:
                    stop_flag.stop()
                    break
                elif key == background_key:
                    stop_flag.send_to_background()
                    print(f"\n{Colors.CYAN}>>> Sending to background...{Colors.END}")
                    break
    except:
        pass
    finally:
        if old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


class InteractiveBot:
    """Interactive menu-driven Travian bot"""

    def __init__(self):
        self.browser = None
        self.session = None
        self.resources = None
        self.buildings = None
        self.military = None
        self.healer = None
        self.running = False
        self.auto_mode = False

        # Initialize loggers
        self.logger = setup_logger('interactive_bot')
        self.action_log = ActionLogger('interactive')

        # Task executor for queued tasks
        self.task_executor = None  # Initialize after browser

        # Settings
        self.settings = {
            'auto_upgrade': True,
            'auto_train': False,
            'upgrade_priority': 'balanced',  # balanced, resources, military
            'check_interval': 60,
            'notify_attacks': True,
        }

    def initialize(self) -> bool:
        """Initialize bot components"""
        print(f"{Colors.YELLOW}Initializing...{Colors.END}")
        self.logger.info("Initializing Interactive Bot...")

        try:
            self.browser = BrowserManager()
            self.browser.start()
            self.logger.info("Browser started")

            self.healer = SelfHealingBot(self.browser)
            self.session = TravianSession(self.browser)
            self.resources = ResourceMonitor(self.browser)
            self.buildings = BuildingManager(self.browser, self.resources)
            self.military = MilitaryManager(self.browser, self.resources)
            self.village_map = VillageMap(self.browser)
            self.village_cycler = VillageCycler(self.browser)
            self.farming = FarmListManager(self.browser)
            self.farm_finder = FarmFinder(self.browser, self.farming)
            self.reports = ReportManager(self.browser)
            self.task_executor = TaskExecutor(self)

            print(f"{Colors.GREEN}✓ Bot initialized{Colors.END}")
            self.logger.info("All components initialized successfully")
            return True

        except Exception as e:
            print(f"{Colors.RED}✗ Initialization failed: {e}{Colors.END}")
            self.logger.error(f"Initialization failed: {e}")
            self.action_log.log_error("initialization", str(e))
            return False

    def login(self) -> bool:
        """Login to Travian"""
        self.logger.info(f"Logging in as {config.username}...")
        result = self.session.login()
        self.action_log.log_login(config.username, result)
        if result:
            self.logger.info("Login successful")
        else:
            self.logger.error("Login failed")
        return result

    def shutdown(self):
        """Clean shutdown"""
        self.logger.info("Shutting down bot...")
        if self.browser:
            self.browser.stop()
        self.logger.info("Bot shutdown complete")
        print(f"\n{Colors.GREEN}✓ Bot stopped. Goodbye!{Colors.END}")

    # ==================== CONNECTION HANDLING ====================

    def wait_for_connection(self, stop_flag=None, max_wait=3600) -> bool:
        """
        Wait for internet connection to be restored.
        Returns True when connected, False if stop_flag triggered or max_wait exceeded.
        """
        start_time = time.time()
        retry_interval = 5  # Start with 5 seconds
        max_retry_interval = 60  # Max 60 seconds between retries

        print(f"\n{Colors.RED}⚠️  Connection lost! Waiting for reconnection...{Colors.END}")
        self.logger.warning("Connection lost, entering reconnection loop")

        while True:
            # Check stop flag
            if stop_flag and stop_flag.should_stop():
                print(f"{Colors.YELLOW}Stop requested, exiting reconnection wait{Colors.END}")
                return False

            # Check max wait time
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                print(f"{Colors.RED}Max wait time exceeded ({max_wait}s){Colors.END}")
                self.logger.error(f"Connection wait exceeded {max_wait}s")
                return False

            # Try to check connection
            try:
                # Simple connectivity test - try to get current URL
                if self.browser and self.browser.driver:
                    _ = self.browser.driver.current_url
                    # If we get here, connection is restored
                    print(f"{Colors.GREEN}✓ Connection restored!{Colors.END}")
                    self.logger.info("Connection restored")

                    # Try to navigate back to game
                    try:
                        self.browser.navigate_to(f"{config.base_url}/dorf1.php")
                        time.sleep(1)
                        # Verify we're logged in
                        if self.session.verify_login():
                            print(f"{Colors.GREEN}✓ Session still valid{Colors.END}")
                            return True
                        else:
                            print(f"{Colors.YELLOW}Session expired, re-logging in...{Colors.END}")
                            if self.session.login():
                                print(f"{Colors.GREEN}✓ Re-login successful{Colors.END}")
                                return True
                            else:
                                print(f"{Colors.RED}Re-login failed, will retry...{Colors.END}")
                    except Exception as e:
                        if is_connection_error(e):
                            pass  # Still no connection, continue waiting
                        else:
                            raise
            except Exception as e:
                if not is_connection_error(e):
                    # Not a connection error, re-raise
                    raise

            # Still disconnected, wait and retry
            mins_elapsed = int(elapsed / 60)
            secs_elapsed = int(elapsed % 60)
            print(f"{Colors.YELLOW}  Disconnected for {mins_elapsed}m {secs_elapsed}s - retrying in {retry_interval}s...{Colors.END}")

            # Sleep in small chunks to check stop flag
            for _ in range(retry_interval):
                if stop_flag and stop_flag.should_stop():
                    return False
                time.sleep(1)

            # Exponential backoff up to max
            retry_interval = min(retry_interval * 2, max_retry_interval)

    def run_with_reconnect(self, func, stop_flag=None, *args, **kwargs):
        """
        Run a function with automatic reconnection on connection errors.
        Returns the function result, or None if stopped or max retries exceeded.
        """
        max_retries = 10
        retries = 0

        while retries < max_retries:
            if stop_flag and stop_flag.should_stop():
                return None

            try:
                return func(*args, **kwargs)
            except Exception as e:
                if is_connection_error(e):
                    retries += 1
                    print(f"\n{Colors.RED}Connection error (attempt {retries}/{max_retries}): {str(e)[:100]}{Colors.END}")
                    self.logger.warning(f"Connection error: {e}")

                    if self.wait_for_connection(stop_flag):
                        print(f"{Colors.GREEN}Retrying operation...{Colors.END}")
                        continue
                    else:
                        return None
                else:
                    # Not a connection error, log and continue
                    print(f"{Colors.RED}Error: {e}{Colors.END}")
                    self.logger.error(f"Non-connection error: {e}")
                    return None

        print(f"{Colors.RED}Max retries ({max_retries}) exceeded{Colors.END}")
        return None

    # ==================== STATUS ====================

    def show_status(self):
        """Display current game status"""
        clear_screen()
        print_header("GAME STATUS")

        # Update data
        self.session.navigate_to_village_overview()
        self.resources.update_resources()
        self.resources.update_production()

        village = self.session.get_current_village()

        print(f"{Colors.BOLD}Village:{Colors.END} {village}")
        print(f"{Colors.BOLD}Server:{Colors.END} {config.server}")
        print()

        # Resources table
        print(f"{Colors.BOLD}Resources:{Colors.END}")
        print(f"  {'Resource':<12} {'Current':>12} {'Capacity':>12} {'Production':>12}")
        print(f"  {'-'*50}")

        res_names = ['wood', 'clay', 'iron', 'crop']
        res_icons = ['🪵', '🧱', '⚒️ ', '🌾']

        for name, icon in zip(res_names, res_icons):
            current = self.resources._format_num(self.resources.resources[name])
            capacity = self.resources._format_num(self.resources.storage_capacity[name])
            prod = self.resources._format_num(self.resources.production[name])
            pct = self.resources.get_storage_percentage(name)

            color = Colors.GREEN if pct < 70 else Colors.YELLOW if pct < 90 else Colors.RED
            print(f"  {icon} {name:<10} {color}{current:>12}{Colors.END} {capacity:>12} {prod:>10}/h")

        print()
        print(f"  🌾 Crop consumption: {self.resources.crop_consumption}")
        print(f"  🌾 Free crop: {self.resources._format_num(self.resources.free_crop)}")

        print()
        input(f"{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== BUILDINGS ====================

    def buildings_menu(self):
        """Buildings management menu"""
        while True:
            clear_screen()
            print_header("BUILDINGS")

            print_menu("Building Options", [
                "View resource fields",
                "View village buildings",
                "Upgrade a building (manual)",
                "Upgrade one resource field",
                "🚀 AUTO UPGRADE ALL RESOURCES TO L20",
                "🏗️  AUTO UPGRADE ALL VILLAGE BUILDINGS TO L20",
                "🌟 AUTO UPGRADE EVERYTHING (resources + buildings)",
                "Scan all buildings",
                "🧠 SMART BUILD ORDER (resources→main→barracks→fill slots→all)",
                "─────── ALL VILLAGES ───────",
                "🌍 AUTO UPGRADE RESOURCES - ALL VILLAGES",
                "🌍 AUTO UPGRADE BUILDINGS - ALL VILLAGES",
                "🌍 SMART BUILD - ALL VILLAGES",
                "─────── DEMOLISH ───────",
                "🗑️  Demolish single building",
                "🗑️  Demolish all of type (e.g. all Crannies)",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.view_resource_fields()
            elif choice == "2":
                self.view_village_buildings()
            elif choice == "3":
                self.manual_upgrade()
            elif choice == "4":
                self.buildings.auto_upgrade_resources(self.session)
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            elif choice == "5":
                self.auto_upgrade_all()
            elif choice == "6":
                self.auto_upgrade_village_buildings()
            elif choice == "7":
                self.auto_upgrade_everything()
            elif choice == "8":
                self.scan_all_buildings()
            elif choice == "9":
                self.smart_build_order()
            elif choice == "10":
                pass  # Separator
            elif choice == "11":
                self.auto_upgrade_all_villages_resources()
            elif choice == "12":
                self.auto_upgrade_all_villages_buildings()
            elif choice == "13":
                self.smart_build_all_villages()
            elif choice == "14":
                pass  # Separator
            elif choice == "15":
                self.demolish_single_building()
            elif choice == "16":
                self.demolish_all_of_type()

    def smart_build_order(self):
        """Smart build order: resources to 10, main to 5, barracks to 3, fill slots, then everything"""
        clear_screen()
        print_header("SMART BUILD ORDER")
        print(f"{Colors.YELLOW}This will upgrade in a smart order:{Colors.END}")
        print(f"  Phase 1: All resource fields to level 10")
        print(f"  Phase 2: Main Building to level 5")
        print(f"  Phase 3: Barracks to level 3")
        print(f"  Phase 4: Auto-fill empty village slots with buildings")
        print(f"  Phase 5: Upgrade everything to level 20")
        print(f"\n{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start smart build order? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Smart build order running...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")

        try:
            total = self.buildings.smart_build_order(stop_flag.should_stop)
        except KeyboardInterrupt:
            stop_flag.stop()
            total = 0

        print(f"\n{Colors.YELLOW}Smart build order stopped{Colors.END}")
        print(f"Total upgrades/constructions: {total}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_upgrade_all_villages_resources(self):
        """Auto upgrade resources in ALL villages - main village to L20, others to L10"""
        clear_screen()
        print_header("AUTO UPGRADE RESOURCES - ALL VILLAGES")

        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            target = "L20" if i == 1 else "L10"
            print(f"  {i}. {v['name']} -> {target}")

        print(f"\n{Colors.YELLOW}Main village (first) -> L20, other villages -> L10{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        villages_completed = 0
        start_village = self.village_cycler.get_current_village()

        try:
            for i, village in enumerate(villages, 1):
                if stop_flag.should_stop():
                    break

                # Main village (first) -> L20, others -> L10
                target_level = 20 if i == 1 else 10

                print(f"\n{'='*60}")
                print(f"VILLAGE {i}/{len(villages)}: {village['name']} -> L{target_level}")
                print(f"{'='*60}")

                if not self.village_cycler.switch_to_village(village['id']):
                    print(f"  Failed to switch to village, skipping...")
                    continue

                # Set target level and upgrade
                old_target = self.buildings.target_level
                self.buildings.target_level = target_level

                village_upgrades = self.buildings.auto_upgrade_all_to_20(self.session, stop_flag.should_stop)
                total_upgrades += village_upgrades

                # Restore target level
                self.buildings.target_level = old_target

                if not stop_flag.should_stop():
                    villages_completed += 1
                    print(f"\n  ✓ {village['name']} COMPLETE - {village_upgrades} upgrades")

        except KeyboardInterrupt:
            stop_flag.stop()

        # Return to original village
        if start_village['id']:
            self.village_cycler.switch_to_village(start_village['id'])

        print(f"\n{'='*60}")
        print(f"{Colors.YELLOW}Stopped{Colors.END}")
        print(f"Villages completed: {villages_completed}/{len(villages)}")
        print(f"Total upgrades: {total_upgrades}")
        print(f"{'='*60}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_upgrade_all_villages_buildings(self):
        """Auto upgrade village buildings in ALL villages - main village L20, others L10"""
        clear_screen()
        print_header("AUTO UPGRADE BUILDINGS - ALL VILLAGES")

        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            target = "L20" if i == 1 else "L10"
            print(f"  {i}. {v['name']} -> {target}")

        print(f"\n{Colors.YELLOW}Main village (first) -> L20, other villages -> L10{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        villages_completed = 0
        start_village = self.village_cycler.get_current_village()

        try:
            for i, village in enumerate(villages, 1):
                if stop_flag.should_stop():
                    break

                # Main village (first) -> L20, others -> L10
                target_level = 20 if i == 1 else 10

                print(f"\n{'='*60}")
                print(f"VILLAGE {i}/{len(villages)}: {village['name']} -> L{target_level}")
                print(f"{'='*60}")

                if not self.village_cycler.switch_to_village(village['id']):
                    print(f"  Failed to switch to village, skipping...")
                    continue

                # Set target level and upgrade
                old_target = self.buildings.target_level
                self.buildings.target_level = target_level

                village_upgrades = self.buildings.auto_upgrade_all_buildings(self.session, stop_flag.should_stop)
                total_upgrades += village_upgrades

                # Restore target level
                self.buildings.target_level = old_target

                if not stop_flag.should_stop():
                    villages_completed += 1
                    print(f"\n  ✓ {village['name']} COMPLETE - {village_upgrades} upgrades")

        except KeyboardInterrupt:
            stop_flag.stop()

        # Return to original village
        if start_village['id']:
            self.village_cycler.switch_to_village(start_village['id'])

        print(f"\n{'='*60}")
        print(f"{Colors.YELLOW}Stopped{Colors.END}")
        print(f"Villages completed: {villages_completed}/{len(villages)}")
        print(f"Total upgrades: {total_upgrades}")
        print(f"{'='*60}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def smart_build_all_villages(self):
        """Run smart build order in ALL villages - main village L20, others L10"""
        clear_screen()
        print_header("SMART BUILD - ALL VILLAGES")

        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            target = "L20" if i == 1 else "L10"
            print(f"  {i}. {v['name']} -> {target}")

        print(f"\n{Colors.YELLOW}Main village (first) -> L20, other villages -> L10{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        villages_completed = 0
        start_village = self.village_cycler.get_current_village()

        try:
            for i, village in enumerate(villages, 1):
                if stop_flag.should_stop():
                    break

                # Main village (first) -> L20, others -> L10
                target_level = 20 if i == 1 else 10

                print(f"\n{'='*60}")
                print(f"VILLAGE {i}/{len(villages)}: {village['name']} -> L{target_level}")
                print(f"{'='*60}")

                if not self.village_cycler.switch_to_village(village['id']):
                    print(f"  Failed to switch to village, skipping...")
                    continue

                # Set target level and run smart build
                old_target = self.buildings.target_level
                self.buildings.target_level = target_level

                village_upgrades = self.buildings.smart_build_order(stop_flag.should_stop)
                total_upgrades += village_upgrades

                # Restore target level
                self.buildings.target_level = old_target

                if not stop_flag.should_stop():
                    villages_completed += 1
                    print(f"\n  ✓ {village['name']} COMPLETE - {village_upgrades} upgrades")

        except KeyboardInterrupt:
            stop_flag.stop()

        # Return to original village
        if start_village['id']:
            self.village_cycler.switch_to_village(start_village['id'])

        print(f"\n{'='*60}")
        print(f"{Colors.YELLOW}Stopped{Colors.END}")
        print(f"Villages completed: {villages_completed}/{len(villages)}")
        print(f"Total upgrades: {total_upgrades}")
        print(f"{'='*60}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def demolish_single_building(self):
        """Demolish a single building"""
        clear_screen()
        print_header("DEMOLISH BUILDING")

        print(f"{Colors.YELLOW}Scanning village buildings...{Colors.END}\n")
        buildings = self.buildings.scan_and_demolish_menu()

        if not buildings:
            print(f"{Colors.RED}No buildings found to demolish{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"  {'#':<4} {'Slot':<6} {'Building':<20} {'Level':<6}")
        print(f"  {'-'*40}")
        for i, b in enumerate(buildings, 1):
            print(f"  {i:<4} {b['slot']:<6} {b['name']:<20} L{b['level']}")

        print()
        choice = get_input("Enter number to demolish (0 to cancel): ")

        try:
            idx = int(choice)
            if idx == 0:
                return
            if 1 <= idx <= len(buildings):
                building = buildings[idx - 1]
                confirm = get_input(f"Demolish {building['name']} at slot #{building['slot']}? (y/n): ")
                if confirm.lower() == 'y':
                    if self.buildings.demolish_building(building['slot'], building['name']):
                        print(f"{Colors.GREEN}✓ Demolish started{Colors.END}")
                    else:
                        print(f"{Colors.RED}✗ Could not demolish{Colors.END}")
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def demolish_all_of_type(self):
        """Demolish all buildings of a specific type"""
        clear_screen()
        print_header("DEMOLISH ALL OF TYPE")

        print(f"{Colors.YELLOW}Scanning village buildings...{Colors.END}\n")
        buildings = self.buildings.scan_and_demolish_menu()

        if not buildings:
            print(f"{Colors.RED}No buildings found{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Count by type
        by_type = {}
        for b in buildings:
            name = b['name']
            if name not in by_type:
                by_type[name] = []
            by_type[name].append(b)

        print(f"  {'#':<4} {'Building Type':<20} {'Count':<6}")
        print(f"  {'-'*35}")
        types_list = list(by_type.items())
        for i, (name, blist) in enumerate(types_list, 1):
            print(f"  {i:<4} {name:<20} {len(blist)}")

        print()
        choice = get_input("Enter number to demolish ALL of that type (0 to cancel): ")

        try:
            idx = int(choice)
            if idx == 0:
                return
            if 1 <= idx <= len(types_list):
                building_type, blist = types_list[idx - 1]
                confirm = get_input(f"Demolish ALL {len(blist)} {building_type}(s)? (y/n): ")
                if confirm.lower() == 'y':
                    print(f"\n{Colors.YELLOW}Demolishing...{Colors.END}")
                    count = self.buildings.demolish_all_of_type(building_type)
                    print(f"{Colors.GREEN}✓ Demolished {count} building(s){Colors.END}")
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def view_resource_fields(self):
        """View all resource fields"""
        clear_screen()
        print_header("RESOURCE FIELDS")

        self.session.navigate_to_village_overview()

        print(f"  {'ID':<4} {'Building':<15} {'Level':<8} {'Can Upgrade':<12}")
        print(f"  {'-'*45}")

        for field_id in range(1, 19):
            info = self.buildings.get_building_info(field_id)
            if info:
                can_up = f"{Colors.GREEN}Yes{Colors.END}" if info['can_upgrade'] else f"{Colors.RED}No{Colors.END}"
                print(f"  {field_id:<4} {info['name']:<15} {info['level']:<8} {can_up}")

        print()
        input(f"{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def view_village_buildings(self):
        """View village center buildings"""
        clear_screen()
        print_header("VILLAGE BUILDINGS")

        self.session.navigate_to_village_center()

        print(f"  {'ID':<4} {'Building':<20} {'Level':<8} {'Can Upgrade':<12}")
        print(f"  {'-'*50}")

        for building_id in range(19, 41):
            info = self.buildings.get_building_info(building_id)
            if info and info['name'] != 'Unknown':
                can_up = f"{Colors.GREEN}Yes{Colors.END}" if info['can_upgrade'] else f"{Colors.RED}No{Colors.END}"
                print(f"  {building_id:<4} {info['name']:<20} {info['level']:<8} {can_up}")

        print()
        input(f"{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def manual_upgrade(self):
        """Manually upgrade a building"""
        clear_screen()
        print_header("MANUAL UPGRADE")

        building_id = get_input("Enter building ID to upgrade (1-40): ")

        try:
            bid = int(building_id)
            if 1 <= bid <= 40:
                info = self.buildings.get_building_info(bid)
                if info:
                    print(f"\n{Colors.BOLD}Building:{Colors.END} {info['name']} Level {info['level']}")
                    print(f"{Colors.BOLD}Upgrade cost:{Colors.END} {info['upgrade_cost']}")
                    print(f"{Colors.BOLD}Can upgrade:{Colors.END} {'Yes' if info['can_upgrade'] else 'No'}")

                    if info['can_upgrade']:
                        confirm = get_input("\nUpgrade this building? (y/n): ")
                        if confirm.lower() == 'y':
                            result = self.buildings.upgrade_building(bid)
                            self.action_log.log_upgrade(
                                info['name'],
                                info['level'],
                                info['level'] + 1,
                                result
                            )
                            self.logger.info(f"Manual upgrade: {info['name']} L{info['level']} -> L{info['level']+1} ({'SUCCESS' if result else 'FAILED'})")
            else:
                print(f"{Colors.RED}Invalid building ID{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_upgrade_all(self):
        """Auto upgrade all resources to level 20"""
        clear_screen()
        print_header("AUTO UPGRADE TO LEVEL 20")
        print(f"{Colors.YELLOW}This will continuously upgrade ALL resource fields to level 20.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop | 'B' to send to background{Colors.END}\n")

        confirm = get_input("Start auto-upgrade? (y/n): ")
        if confirm.lower() == 'y':
            stop_flag = StopFlag()
            self._auto_upgrade_with_stop(stop_flag)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _auto_upgrade_with_stop(self, stop_flag: StopFlag, is_background: bool = False) -> int:
        """Auto upgrade all resources with stop flag support"""
        if not is_background:
            print("=" * 50)
            print(f"🚀 AUTO UPGRADE ALL RESOURCES TO LEVEL 20")
            print(f"{Colors.RED}>>> Press 'Q'/'S' to stop | 'B' for background <<<{Colors.END}")
            print("=" * 50)

            # Start key listener
            listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
            listener_thread.start()

        total_upgrades = 0
        rounds = 0
        target_level = 20

        try:
            while not stop_flag.should_stop():
                # Check if sent to background - use Task Queue instead
                if not is_background and stop_flag.is_background():
                    print(f"\n{Colors.CYAN}Background mode: Use 'Task Queue' menu to add upgrade tasks.{Colors.END}")
                    print(f"{Colors.YELLOW}The task queue runs tasks sequentially (Selenium limitation).{Colors.END}")
                    time.sleep(2)
                    return total_upgrades

                rounds += 1
                if not is_background:
                    print(f"\n--- Round {rounds} ---")

                all_done = True
                upgraded_this_round = 0

                for field_id in range(1, 19):
                    if stop_flag.should_stop():
                        break

                    self.buildings.navigate_to_building(field_id)

                    h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
                    level = 0
                    name = f"Field #{field_id}"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))

                    if level < target_level:
                        all_done = False

                        upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')

                        if upgrade_btn:
                            btn_class = upgrade_btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                if not is_background:
                                    print(f"🔨 {name} L{level} -> L{level+1}")
                                upgrade_btn.click()
                                total_upgrades += 1
                                upgraded_this_round += 1

                if not is_background:
                    print(f"Upgraded {upgraded_this_round} fields this round")
                    print(f"Total upgrades: {total_upgrades}")
                    print(f"{Colors.RED}[Q/S=stop | B=background]{Colors.END}")

                if all_done:
                    if not is_background:
                        print(f"\n🎉 ALL FIELDS AT LEVEL {target_level}!")
                    break

                if upgraded_this_round == 0 and not stop_flag.should_stop():
                    if not is_background:
                        print("No upgrades available, waiting 5s...")
                    for _ in range(5):
                        if stop_flag.should_stop():
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            if not is_background:
                print(f"Error: {e}")

        if not is_background:
            print(f"\n{'='*50}")
            print(f"✓ Total upgrades performed: {total_upgrades}")
            print(f"{'='*50}")
            self.logger.info(f"Auto-upgrade completed: {total_upgrades} upgrades")

        return total_upgrades

    def auto_upgrade_village_buildings(self):
        """Auto upgrade all village buildings to max level"""
        clear_screen()
        print_header("AUTO UPGRADE VILLAGE BUILDINGS")
        print(f"{Colors.YELLOW}This will continuously upgrade ALL village buildings to level 20.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start auto-upgrade village buildings? (y/n): ")
        if confirm.lower() == 'y':
            stop_flag = StopFlag()
            self._auto_upgrade_village_with_stop(stop_flag)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _auto_upgrade_village_with_stop(self, stop_flag: StopFlag) -> int:
        """Auto upgrade village buildings with stop flag support"""
        print("=" * 50)
        print(f"🏗️ AUTO UPGRADE VILLAGE BUILDINGS TO LEVEL 20")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        # Start key listener
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        rounds = 0
        target_level = 20

        try:
            while not stop_flag.should_stop():
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                all_done = True
                upgraded_this_round = 0
                buildings_status = []

                for building_id in range(19, 41):
                    if stop_flag.should_stop():
                        break

                    self.buildings.navigate_to_building(building_id)

                    h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
                    level = 0
                    name = "Empty"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()[:15]
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))
                        elif text.strip() and 'Construct' not in text:
                            name = text.strip()[:15]

                    # Skip empty slots
                    if name in ['Empty', 'Unknown'] or 'Construct' in name:
                        continue

                    if level < target_level:
                        all_done = False

                        # Try to upgrade
                        upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                        if upgrade_btn:
                            btn_class = upgrade_btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                print(f"🏗️ {name} L{level} -> L{level+1}")
                                upgrade_btn.click()
                                total_upgrades += 1
                                upgraded_this_round += 1

                    buildings_status.append((building_id, name, level))

                print(f"Upgraded {upgraded_this_round} buildings this round")
                print(f"Total upgrades: {total_upgrades}")
                print(f"{Colors.RED}[Q/S=stop]{Colors.END}")

                if all_done:
                    print(f"\n🎉 ALL BUILDINGS AT LEVEL {target_level}!")
                    break

                if upgraded_this_round == 0 and not stop_flag.should_stop():
                    print("No upgrades available, waiting 5s...")
                    for _ in range(5):
                        if stop_flag.should_stop():
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n{'='*50}")
        print(f"✓ Total building upgrades: {total_upgrades}")
        print(f"{'='*50}")
        self.logger.info(f"Village building upgrade completed: {total_upgrades} upgrades")

        return total_upgrades

    def auto_upgrade_everything(self):
        """Auto upgrade both resources and village buildings"""
        clear_screen()
        print_header("AUTO UPGRADE EVERYTHING")
        print(f"{Colors.YELLOW}This will continuously upgrade ALL resources AND village buildings to level 20.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start auto-upgrade everything? (y/n): ")
        if confirm.lower() == 'y':
            stop_flag = StopFlag()
            self._auto_upgrade_everything_with_stop(stop_flag)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _auto_upgrade_everything_with_stop(self, stop_flag: StopFlag) -> int:
        """Auto upgrade everything with stop flag support"""
        print("=" * 50)
        print(f"🌟 AUTO UPGRADE EVERYTHING TO LEVEL 20")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        # Start key listener
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        rounds = 0
        target_level = 20

        try:
            while not stop_flag.should_stop():
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                all_done = True
                upgraded_this_round = 0

                # First: Resource fields (1-18)
                print(f"{Colors.CYAN}[Resources]{Colors.END}")
                for field_id in range(1, 19):
                    if stop_flag.should_stop():
                        break

                    self.buildings.navigate_to_building(field_id)

                    h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
                    level = 0
                    name = f"Field #{field_id}"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))

                    if level < target_level:
                        all_done = False

                        upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                        if upgrade_btn:
                            btn_class = upgrade_btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                print(f"🔨 {name} L{level} -> L{level+1}")
                                upgrade_btn.click()
                                total_upgrades += 1
                                upgraded_this_round += 1

                # Second: Village buildings (19-40)
                print(f"{Colors.CYAN}[Buildings]{Colors.END}")
                for building_id in range(19, 41):
                    if stop_flag.should_stop():
                        break

                    self.buildings.navigate_to_building(building_id)

                    h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
                    level = 0
                    name = "Empty"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()[:15]
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))
                        elif text.strip() and 'Construct' not in text:
                            name = text.strip()[:15]

                    # Skip empty slots
                    if name in ['Empty', 'Unknown'] or 'Construct' in name:
                        continue

                    if level < target_level:
                        all_done = False

                        upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                        if upgrade_btn:
                            btn_class = upgrade_btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                print(f"🏗️ {name} L{level} -> L{level+1}")
                                upgrade_btn.click()
                                total_upgrades += 1
                                upgraded_this_round += 1

                print(f"\nUpgraded {upgraded_this_round} this round | Total: {total_upgrades}")
                print(f"{Colors.RED}[Q/S=stop]{Colors.END}")

                if all_done:
                    print(f"\n🎉 EVERYTHING AT LEVEL {target_level}!")
                    break

                if upgraded_this_round == 0 and not stop_flag.should_stop():
                    print("No upgrades available, waiting 5s...")
                    for _ in range(5):
                        if stop_flag.should_stop():
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n{'='*50}")
        print(f"✓ Total upgrades: {total_upgrades}")
        print(f"{'='*50}")
        self.logger.info(f"Full upgrade completed: {total_upgrades} upgrades")

        return total_upgrades

    def scan_all_buildings(self):
        """Scan and display all buildings"""
        clear_screen()
        print_header("SCANNING ALL BUILDINGS")
        print(f"{Colors.CYAN}Resource Fields:{Colors.END}")
        self.buildings.scan_all_fields()
        print(f"\n{Colors.CYAN}Village Buildings:{Colors.END}")
        self.buildings.scan_village_buildings()
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== MILITARY ====================

    def military_menu(self):
        """Military management menu"""
        while True:
            clear_screen()
            print_header("MILITARY")

            print_menu("Military Options", [
                "View troops",
                "🗡️  Train troops (choose type & amount)",
                "🔄 AUTO TRAIN (continuous single troop)",
                "🌍 MULTI-VILLAGE TRAINING SETUP",
                "🌍 TRAIN ALL VILLAGES NOW",
                "🌍 AUTO TRAIN ALL VILLAGES (continuous)",
                "⚔️  Send attack",
                "🎯 Send raid",
                "⚠️  Check incoming attacks",
                "🔨 AUTO SMITHY (upgrade all troops)",
                "🔬 AUTO ACADEMY (research all)",
                "🎉 AUTO CELEBRATIONS (town hall)",
                "🌍🔨 MULTI-VILLAGE SMITHY (all villages)",
                "🌍🔬 MULTI-VILLAGE ACADEMY (all villages)",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.view_troops()
            elif choice == "2":
                self.train_max_troops()
            elif choice == "3":
                self.auto_train_continuous()
            elif choice == "4":
                self.multi_village_training_setup()
            elif choice == "5":
                self.train_all_villages_now()
            elif choice == "6":
                self.auto_train_all_villages()
            elif choice == "7":
                self.send_attack_menu()
            elif choice == "8":
                self.send_raid_menu()
            elif choice == "9":
                self.check_incoming()
            elif choice == "10":
                self.auto_smithy()
            elif choice == "11":
                self.auto_academy()
            elif choice == "12":
                self.auto_celebrations()
            elif choice == "13":
                self.multi_village_smithy()
            elif choice == "14":
                self.multi_village_academy()

    def auto_smithy(self):
        """Auto upgrade all troops in the smithy"""
        clear_screen()
        print_header("AUTO SMITHY")
        print(f"{Colors.YELLOW}This will continuously upgrade troop levels in the Smithy.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start auto-smithy? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Auto-smithy running...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        try:
            total = self.military.auto_smithy_loop(stop_flag.should_stop)
        except KeyboardInterrupt:
            stop_flag.stop()
            total = 0

        print(f"\n{Colors.YELLOW}Auto-smithy stopped{Colors.END}")
        print(f"Total upgrades queued: {total}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_academy(self):
        """Auto research all troops in the academy"""
        clear_screen()
        print_header("AUTO ACADEMY")
        print(f"{Colors.YELLOW}This will continuously research troops in the Academy.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        confirm = get_input("Start auto-academy? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Auto-academy running...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        try:
            total = self.military.auto_academy_loop(stop_flag.should_stop)
        except KeyboardInterrupt:
            stop_flag.stop()
            total = 0

        print(f"\n{Colors.YELLOW}Auto-academy stopped{Colors.END}")
        print(f"Total researches queued: {total}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_celebrations(self):
        """Auto start celebrations in the town hall"""
        clear_screen()
        print_header("AUTO CELEBRATIONS")
        print(f"{Colors.YELLOW}This will continuously start celebrations in the Town Hall.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        print("Celebration type:")
        print("  1. Great Celebration (big)")
        print("  2. Small Celebration")
        cel_choice = get_input("Choice (default 1): ")
        big = cel_choice != '2'

        interval = get_input("Check interval in seconds (default 60): ")
        try:
            interval = int(interval) if interval else 60
        except ValueError:
            interval = 60

        label = "Great" if big else "Small"
        confirm = get_input(f"\nStart auto {label} celebrations every {interval}s? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Auto-celebrations running ({label}, interval {interval}s)...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        try:
            total = self.military.auto_celebration_loop(stop_flag.should_stop, big=big, interval=interval)
        except KeyboardInterrupt:
            stop_flag.stop()
            total = 0

        print(f"\n{Colors.YELLOW}Auto-celebrations stopped{Colors.END}")
        print(f"Total celebrations started: {total}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def multi_village_smithy(self):
        """Upgrade smithy troops across all villages"""
        clear_screen()
        print_header("MULTI-VILLAGE SMITHY")

        print(f"{Colors.YELLOW}Scanning for villages...{Colors.END}\n")
        villages = self.village_cycler.get_all_villages(force_refresh=True)

        if not villages:
            print(f"{Colors.RED}No villages found{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.GREEN}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            print(f"  {i}. {v['name']}")

        print(f"\n{Colors.YELLOW}Will upgrade smithy troops in each village sequentially.{Colors.END}")

        mode = get_input("\n1. Run once  2. Continuous (auto)  (default 1): ")
        if mode == '2':
            interval = get_input("Interval between cycles in seconds (default 60): ")
            try:
                interval = int(interval) if interval else 60
            except ValueError:
                interval = 60

            confirm = get_input(f"\nStart auto multi-village smithy every {interval}s? (y/n): ")
            if confirm.lower() != 'y':
                return

            stop_flag = StopFlag()
            listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
            listener_thread.start()

            print(f"\n{Colors.GREEN}Multi-village smithy running...{Colors.END}")
            print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
            print("=" * 50)

            total_upgrades = 0
            cycles = 0
            try:
                while not stop_flag.should_stop():
                    cycles += 1
                    print(f"\n{Colors.CYAN}--- Smithy Cycle {cycles} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")
                    results = self.military.multi_village_smithy_cycle(villages)
                    total_upgrades += results['total_upgrades']
                    print(f"\nCycle upgrades: {results['total_upgrades']} | Total: {total_upgrades}")

                    if stop_flag.should_stop():
                        break

                    print(f"Next cycle in {interval}s... {Colors.RED}[Q/S=stop]{Colors.END}")
                    for _ in range(interval):
                        if stop_flag.should_stop():
                            break
                        time.sleep(1)
            except KeyboardInterrupt:
                stop_flag.stop()

            print(f"\n{Colors.YELLOW}Multi-village smithy stopped{Colors.END}")
            print(f"Total cycles: {cycles} | Total upgrades: {total_upgrades}")
        else:
            confirm = get_input(f"\nRun smithy upgrades in {len(villages)} village(s)? (y/n): ")
            if confirm.lower() != 'y':
                return

            results = self.military.multi_village_smithy_cycle(villages)
            print(f"\n{Colors.GREEN}Done! {results['total_upgrades']} upgrade(s) queued across {results['villages_processed']} village(s){Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def multi_village_academy(self):
        """Research academy troops across all villages"""
        clear_screen()
        print_header("MULTI-VILLAGE ACADEMY")

        print(f"{Colors.YELLOW}Scanning for villages...{Colors.END}\n")
        villages = self.village_cycler.get_all_villages(force_refresh=True)

        if not villages:
            print(f"{Colors.RED}No villages found{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.GREEN}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            print(f"  {i}. {v['name']}")

        print(f"\n{Colors.YELLOW}Will research academy troops in each village sequentially.{Colors.END}")

        mode = get_input("\n1. Run once  2. Continuous (auto)  (default 1): ")
        if mode == '2':
            interval = get_input("Interval between cycles in seconds (default 60): ")
            try:
                interval = int(interval) if interval else 60
            except ValueError:
                interval = 60

            confirm = get_input(f"\nStart auto multi-village academy every {interval}s? (y/n): ")
            if confirm.lower() != 'y':
                return

            stop_flag = StopFlag()
            listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
            listener_thread.start()

            print(f"\n{Colors.GREEN}Multi-village academy running...{Colors.END}")
            print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
            print("=" * 50)

            total_researches = 0
            cycles = 0
            try:
                while not stop_flag.should_stop():
                    cycles += 1
                    print(f"\n{Colors.CYAN}--- Academy Cycle {cycles} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")
                    results = self.military.multi_village_academy_cycle(villages)
                    total_researches += results['total_researches']
                    print(f"\nCycle researches: {results['total_researches']} | Total: {total_researches}")

                    if stop_flag.should_stop():
                        break

                    print(f"Next cycle in {interval}s... {Colors.RED}[Q/S=stop]{Colors.END}")
                    for _ in range(interval):
                        if stop_flag.should_stop():
                            break
                        time.sleep(1)
            except KeyboardInterrupt:
                stop_flag.stop()

            print(f"\n{Colors.YELLOW}Multi-village academy stopped{Colors.END}")
            print(f"Total cycles: {cycles} | Total researches: {total_researches}")
        else:
            confirm = get_input(f"\nRun academy research in {len(villages)} village(s)? (y/n): ")
            if confirm.lower() != 'y':
                return

            results = self.military.multi_village_academy_cycle(villages)
            print(f"\n{Colors.GREEN}Done! {results['total_researches']} research(es) queued across {results['villages_processed']} village(s){Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def view_troops(self):
        """View current troops"""
        clear_screen()
        print_header("TROOPS")
        troops = self.military.get_troop_counts()
        if troops:
            for troop, count in troops.items():
                print(f"  {troop}: {count}")
        else:
            print("  No troops data available")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def train_max_troops(self):
        """Train maximum troops - choose which troop type"""
        clear_screen()
        print_header("TRAIN MAX TROOPS")

        print("Select building:")
        print("  1. Barracks (infantry)")
        print("  2. Stable (cavalry)")

        choice = get_input("Building: ")

        building = 'barracks' if choice == '1' else 'stable' if choice == '2' else 'barracks'

        print(f"\n{Colors.YELLOW}Navigating to {building}...{Colors.END}")

        if building == 'barracks':
            if not self.military.navigate_to_barracks():
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return
        else:
            if not self.military.navigate_to_stable():
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return

        # Get available troops
        print(f"\n{Colors.YELLOW}Scanning available troops...{Colors.END}\n")
        available = self.military.get_available_troops_to_train()

        if not available:
            print(f"{Colors.RED}No troops found to train{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Show options
        print(f"{Colors.GREEN}Available troops:{Colors.END}")
        for i, troop in enumerate(available, 1):
            max_str = f"(max: {troop['max']})" if troop['max'] > 0 else ""
            print(f"  {i}. {troop['name']} {max_str}")

        print(f"  0. Cancel")

        troop_choice = get_input("\nWhich troop to train? ")

        try:
            idx = int(troop_choice)
            if idx == 0:
                return
            if 1 <= idx <= len(available):
                selected = available[idx - 1]

                # Ask for amount
                if selected['max'] > 0:
                    amount_str = get_input(f"Amount (max {selected['max']}, or 'max'): ")
                    if amount_str.lower() == 'max':
                        amount = selected['max']
                    else:
                        amount = int(amount_str)
                else:
                    amount_str = get_input("Amount (or 'max' for maximum): ")
                    if amount_str.lower() == 'max':
                        amount = 99999999
                    else:
                        amount = int(amount_str)

                # Train
                print(f"\n{Colors.YELLOW}Training {amount}x {selected['name']}...{Colors.END}")
                self.military.train_single_troop(selected, amount)

        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_train_continuous(self):
        """Continuously train troops automatically"""
        clear_screen()
        print_header("AUTO TRAIN TROOPS")

        print(f"{Colors.YELLOW}This will continuously train ONE troop type until you stop it.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop | 'B' to send to background{Colors.END}\n")

        print("Select building:")
        print("  1. Barracks (infantry)")
        print("  2. Stable (cavalry)")

        choice = get_input("Building: ")
        building = 'barracks' if choice == '1' else 'stable' if choice == '2' else 'barracks'

        print(f"\n{Colors.YELLOW}Navigating to {building}...{Colors.END}")

        if building == 'barracks':
            if not self.military.navigate_to_barracks():
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return
        else:
            if not self.military.navigate_to_stable():
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return

        # Get available troops and let user choose
        print(f"\n{Colors.YELLOW}Scanning available troops...{Colors.END}\n")
        available = self.military.get_available_troops_to_train()

        if not available:
            print(f"{Colors.RED}No troops found to train{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.GREEN}Available troops:{Colors.END}")
        for i, troop in enumerate(available, 1):
            max_str = f"(max: {troop['max']})" if troop['max'] > 0 else ""
            print(f"  {i}. {troop['name']} {max_str}")

        troop_choice = get_input("\nWhich troop to auto-train? ")

        try:
            idx = int(troop_choice)
            if idx < 1 or idx > len(available):
                print(f"{Colors.RED}Invalid choice{Colors.END}")
                return
            selected_troop = available[idx - 1]
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")
            return

        interval = get_input("Check interval in seconds (default 30): ")
        try:
            interval = int(interval) if interval else 30
        except ValueError:
            interval = 30

        confirm = get_input(f"\nAuto-train {selected_troop['name']} continuously? (y/n): ")
        if confirm.lower() != 'y':
            return

        # Start the training loop
        stop_flag = StopFlag()
        self._run_auto_train_loop(building, selected_troop, interval, stop_flag)

    def _run_auto_train_loop(self, building: str, selected_troop: Dict, interval: int, stop_flag: StopFlag, is_background: bool = False):
        """The actual auto-train loop (can run in foreground or background)"""
        if not is_background:
            print(f"\n{Colors.GREEN}Starting auto-train...{Colors.END}")
            print(f"Troop: {selected_troop['name']}")
            print(f"Check interval: {interval}s")
            print(f"\n{Colors.RED}>>> Press 'Q'/'S' to stop | 'B' for background <<<{Colors.END}")
            print("=" * 50)

            # Start key listener thread
            listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
            listener_thread.start()

        total_trained = 0
        rounds = 0

        try:
            while not stop_flag.should_stop():
                # Check if sent to background - use Task Queue instead
                if not is_background and stop_flag.is_background():
                    print(f"\n{Colors.CYAN}Background mode: Use 'Task Queue' menu to add training tasks.{Colors.END}")
                    print(f"{Colors.YELLOW}The task queue runs tasks sequentially (Selenium limitation).{Colors.END}")
                    time.sleep(2)
                    return

                rounds += 1
                if not is_background:
                    print(f"\n{Colors.CYAN}--- Round {rounds} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")

                # Navigate back to building
                if building == 'barracks':
                    self.military.navigate_to_barracks()
                else:
                    self.military.navigate_to_stable()

                # Re-scan to get fresh input element
                available = self.military.get_available_troops_to_train()

                # Find our selected troop again
                current_troop = None
                for t in available:
                    if t['name'] == selected_troop['name'] or t['input_name'] == selected_troop['input_name']:
                        current_troop = t
                        break

                if current_troop and current_troop['max'] > 0:
                    if not is_background:
                        print(f"  Training {current_troop['max']}x {current_troop['name']}...")
                    if self.military.train_single_troop(current_troop, current_troop['max']):
                        total_trained += current_troop['max']
                        if not is_background:
                            print(f"  ✓ Total trained: {total_trained}")
                else:
                    if not is_background:
                        print(f"  No {selected_troop['name']} available to train")

                if not is_background:
                    print(f"{Colors.RED}[Q/S=stop | B=background]{Colors.END}")

                if stop_flag.should_stop():
                    break

                # Wait with periodic stop checks
                for _ in range(interval):
                    if stop_flag.should_stop():
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            if not is_background:
                print(f"Error: {e}")

        if not is_background:
            print(f"\n\n{Colors.YELLOW}Auto-train stopped{Colors.END}")
            print(f"\n{'='*50}")
            print(f"Troop: {selected_troop['name']}")
            print(f"Total rounds: {rounds}")
            print(f"Total troops trained: {total_trained}")
            print(f"{'='*50}")
            self.logger.info(f"Auto-train completed: {total_trained} {selected_troop['name']} in {rounds} rounds")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== MULTI-VILLAGE TRAINING ====================

    def multi_village_training_setup(self):
        """Setup training configuration for all villages"""
        clear_screen()
        print_header("MULTI-VILLAGE TRAINING SETUP")

        # Get all villages (use village_cycler which reliably finds all villages)
        print(f"{Colors.YELLOW}Scanning for villages...{Colors.END}\n")
        villages = self.village_cycler.get_all_villages(force_refresh=True)

        if not villages:
            print(f"{Colors.RED}No villages found{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.GREEN}Found {len(villages)} village(s):{Colors.END}")
        for i, v in enumerate(villages, 1):
            print(f"  {i}. {v['name']}")

        # Load existing configs
        configs = self.military.load_village_training_configs()

        print_menu("Setup Options", [
            "Configure ALL villages (guided setup)",
            "Configure a single village",
            "View current configuration",
            "Enable/disable a village",
            "Clear all configurations",
        ])

        choice = get_input()

        if choice == "1":
            self.configure_all_villages(villages, configs)
        elif choice == "2":
            self.configure_single_village(villages, configs)
        elif choice == "3":
            self.military.print_training_configs(configs)
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
        elif choice == "4":
            self.toggle_village_training(configs)
        elif choice == "5":
            confirm = get_input("Clear all training configs? (y/n): ")
            if confirm.lower() == 'y':
                configs = {}
                self.military.save_village_training_configs(configs)
                print(f"{Colors.GREEN}✓ All configs cleared{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def configure_all_villages(self, villages: List[Dict], configs: Dict):
        """Configure training for all villages"""
        clear_screen()
        print_header("CONFIGURE ALL VILLAGES")

        print(f"{Colors.YELLOW}This will guide you through setting up training for each village.{Colors.END}")
        print(f"{Colors.YELLOW}For each village, you'll choose which troops to train.{Colors.END}\n")

        confirm = get_input("Start configuration? (y/n): ")
        if confirm.lower() != 'y':
            return

        for village in villages:
            cfg = self.military.configure_village_training(village)
            if cfg:
                configs[village['id']] = cfg

        # Save configurations
        self.military.save_village_training_configs(configs)

        print(f"\n{'='*50}")
        print(f"{Colors.GREEN}✓ Configuration complete for {len(configs)} village(s)!{Colors.END}")
        print(f"{'='*50}")

        self.military.print_training_configs(configs)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def configure_single_village(self, villages: List[Dict], configs: Dict):
        """Configure training for a single village"""
        clear_screen()
        print_header("CONFIGURE SINGLE VILLAGE")

        print("Select village to configure:\n")
        for i, v in enumerate(villages, 1):
            existing = "✓" if v['id'] in configs else ""
            print(f"  {i}. {v['name']} {existing}")

        choice = get_input("\nVillage number: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(villages):
                village = villages[idx]
                cfg = self.military.configure_village_training(village)
                if cfg:
                    configs[village['id']] = cfg
                    self.military.save_village_training_configs(configs)
                    print(f"\n{Colors.GREEN}✓ Configuration saved for {village['name']}{Colors.END}")
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def toggle_village_training(self, configs: Dict):
        """Enable/disable training for a village"""
        clear_screen()
        print_header("TOGGLE VILLAGE TRAINING")

        if not configs:
            print(f"{Colors.RED}No villages configured{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        self.military.print_training_configs(configs)

        village_name = get_input("\nEnter village name to toggle: ")

        for vid, cfg in configs.items():
            if village_name.lower() in cfg.village_name.lower():
                cfg.enabled = not cfg.enabled
                self.military.save_village_training_configs(configs)
                status = "enabled" if cfg.enabled else "disabled"
                print(f"{Colors.GREEN}✓ {cfg.village_name} training {status}{Colors.END}")
                break
        else:
            print(f"{Colors.RED}Village not found{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def train_all_villages_now(self):
        """Train troops in all configured villages immediately"""
        clear_screen()
        print_header("TRAIN ALL VILLAGES")

        # Load configs
        configs = self.military.load_village_training_configs()

        if not configs:
            print(f"{Colors.RED}No villages configured!{Colors.END}")
            print(f"Use 'Multi-Village Training Setup' first.")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        enabled = [c for c in configs.values() if c.enabled]
        print(f"Will train in {len(enabled)} village(s):\n")

        self.military.print_training_configs(configs)

        confirm = get_input(f"\n{Colors.YELLOW}Start training? (y/n): {Colors.END}")
        if confirm.lower() != 'y':
            return

        print(f"\n{Colors.GREEN}Training in progress...{Colors.END}")
        results = self.military.multi_village_training_cycle(configs)

        print(f"\n{'='*50}")
        print(f"✓ Trained in {results['villages_trained']} village(s)")
        print(f"  Barracks: {results['total_barracks']} troops")
        print(f"  Stable: {results['total_stable']} troops")
        print(f"{'='*50}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_train_all_villages(self):
        """Continuously train troops in all villages"""
        clear_screen()
        print_header("AUTO TRAIN ALL VILLAGES")

        # Load configs
        configs = self.military.load_village_training_configs()

        if not configs:
            print(f"{Colors.RED}No villages configured!{Colors.END}")
            print(f"Use 'Multi-Village Training Setup' first.")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        enabled = [c for c in configs.values() if c.enabled]
        print(f"{Colors.YELLOW}Will continuously train in {len(enabled)} village(s).{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        self.military.print_training_configs(configs)

        interval = get_input(f"\nTraining interval in seconds (default 60): ")
        try:
            interval = int(interval) if interval else 60
        except ValueError:
            interval = 60

        confirm = get_input(f"\nStart auto-training every {interval}s? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        self._run_multi_village_train_loop(configs, interval, stop_flag)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _run_multi_village_train_loop(self, configs: Dict, interval: int, stop_flag: StopFlag):
        """The actual multi-village training loop"""
        print(f"\n{Colors.GREEN}Starting multi-village training...{Colors.END}")
        print(f"Interval: {interval}s")
        print(f"\n{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        # Start key listener thread
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_barracks = 0
        total_stable = 0
        cycles = 0

        try:
            while not stop_flag.should_stop():
                cycles += 1
                print(f"\n{Colors.CYAN}--- Training Cycle {cycles} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")

                results = self.military.multi_village_training_cycle(configs)

                total_barracks += results['total_barracks']
                total_stable += results['total_stable']

                print(f"\nCycle totals: Barracks={results['total_barracks']}, Stable={results['total_stable']}")
                print(f"Overall totals: Barracks={total_barracks}, Stable={total_stable}")
                print(f"{Colors.RED}[Q/S=stop]{Colors.END}")

                if stop_flag.should_stop():
                    break

                # Wait with periodic stop checks
                print(f"Next cycle in {interval}s...")
                for _ in range(interval):
                    if stop_flag.should_stop():
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n\n{Colors.YELLOW}Multi-village training stopped{Colors.END}")
        print(f"\n{'='*50}")
        print(f"Total cycles: {cycles}")
        print(f"Total barracks troops: {total_barracks}")
        print(f"Total stable troops: {total_stable}")
        print(f"{'='*50}")
        self.logger.info(f"Multi-village training: {total_barracks} barracks + {total_stable} stable in {cycles} cycles")

    def send_attack_menu(self):
        """Send attack interface"""
        clear_screen()
        print_header("SEND ATTACK")

        x = get_input("Target X coordinate: ")
        y = get_input("Target Y coordinate: ")

        try:
            target_x = int(x)
            target_y = int(y)

            confirm = get_input(f"\nSend attack to ({target_x}, {target_y})? (y/n): ")
            if confirm.lower() == 'y':
                result = self.military.send_attack(target_x, target_y, {})
                self.action_log.log_attack(target_x, target_y, {}, result)
                self.logger.info(f"Attack sent to ({target_x}, {target_y}): {'SUCCESS' if result else 'FAILED'}")
        except ValueError:
            print(f"{Colors.RED}Invalid coordinates{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def send_raid_menu(self):
        """Send raid interface"""
        clear_screen()
        print_header("SEND RAID")
        print("Raid functionality - similar to attack but for farming")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def check_incoming(self):
        """Check for incoming attacks"""
        clear_screen()
        print_header("INCOMING ATTACKS")
        incoming = self.military.check_incoming_attacks()
        if incoming:
            print(f"{Colors.RED}⚠️  {len(incoming)} INCOMING ATTACK(S)!{Colors.END}")
            for attack in incoming:
                print(f"  - {attack}")
        else:
            print(f"{Colors.GREEN}✓ No incoming attacks detected{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== FARMING ====================

    def farming_menu(self):
        """Farm list management menu"""
        while True:
            clear_screen()
            print_header("FARM LIST MANAGER")

            # Show farm count
            total = len(self.farming.get_all_farms())
            enabled = len(self.farming.get_enabled_farms())
            lists_count = len(self.farming.farm_lists)
            print(f"{Colors.GREEN}Active list: {self.farming.active_list_name} | Farms: {enabled}/{total} enabled | Lists: {lists_count}{Colors.END}\n")

            print_menu("Farming Options", [
                "📋 View farm list",
                "➕ Add farm manually",
                "➕ Add farm from map coordinates",
                "✏️  Edit farm troops",
                "🔄 Toggle farm on/off",
                "❌ Remove farm",
                "⚙️  Set default troops",
                "✏️  Change ALL farm troops",
                "🚀 SEND ALL RAIDS NOW",
                "🔄 AUTO FARM (continuous)",
                "⏱️  AUTO RAID (travel-time based)",
                "📊 Farm statistics",
                "--- Farm Lists ---",
                "📋 View all farm lists",
                "➕ Create new farm list",
                "🔄 Switch active farm list",
                "❌ Delete farm list",
                "↔️  Move farm to another list",
                "--- Farm Finder ---",
                "🔍 Scan for farms (auto finder)",
                "🗑️  Clear scan history",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.view_farm_list()
            elif choice == "2":
                self.add_farm_manual()
            elif choice == "3":
                self.add_farm_from_map()
            elif choice == "4":
                self.edit_farm_troops()
            elif choice == "5":
                self.toggle_farm()
            elif choice == "6":
                self.remove_farm()
            elif choice == "7":
                self.set_default_troops()
            elif choice == "8":
                self.change_all_farm_troops()
            elif choice == "9":
                self.send_all_raids()
            elif choice == "10":
                self.auto_farm_continuous()
            elif choice == "11":
                self.auto_raid_travel_time()
            elif choice == "12":
                self.farm_statistics()
            elif choice == "13":
                pass  # separator
            elif choice == "14":
                self.view_all_farm_lists()
            elif choice == "15":
                self.create_farm_list()
            elif choice == "16":
                self.switch_farm_list()
            elif choice == "17":
                self.delete_farm_list()
            elif choice == "18":
                self.move_farm_to_list()
            elif choice == "19":
                pass  # separator
            elif choice == "20":
                self.scan_for_farms()
            elif choice == "21":
                self.clear_scan_history()

    def view_farm_list(self):
        """View all farms in the list"""
        clear_screen()
        print_header("FARM LIST")
        self.farming.print_farm_list()

        # Ask if user wants to see details
        farm_id = get_input("\nEnter farm ID for details (or Enter to go back): ")
        if farm_id:
            try:
                self.farming.print_farm_details(int(farm_id))
            except ValueError:
                pass

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def add_farm_manual(self):
        """Add a farm manually"""
        clear_screen()
        print_header("ADD FARM")

        name = get_input("Farm name (e.g., 'Oasis North'): ")
        if not name:
            return

        x = get_input("X coordinate: ")
        y = get_input("Y coordinate: ")

        try:
            x = int(x)
            y = int(y)
        except ValueError:
            print(f"{Colors.RED}Invalid coordinates{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        notes = get_input("Notes (optional): ")

        # Ask if user wants to set troops now or use default
        use_default = get_input("Use default troops? (y/n): ")

        if use_default.lower() == 'y':
            troops = None  # Will use default
        else:
            troops = self.configure_troops()

        self.farming.add_farm(name, x, y, troops, notes)
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def add_farm_from_map(self):
        """Add a farm by clicking on the map or entering coordinates"""
        clear_screen()
        print_header("ADD FARM FROM MAP")

        print("Enter the coordinates of the village/oasis to add:\n")

        x = get_input("X coordinate: ")
        y = get_input("Y coordinate: ")

        try:
            x = int(x)
            y = int(y)
        except ValueError:
            print(f"{Colors.RED}Invalid coordinates{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Navigate to the position to get info
        print(f"\n{Colors.YELLOW}Checking ({x}|{y})...{Colors.END}")
        self.browser.navigate_to(f"{config.base_url}/position_details.php?x={x}&y={y}")

        # Try to get the name from the page
        name = f"Farm ({x}|{y})"
        try:
            title = self.browser.find_element_fast(By.CSS_SELECTOR, '#tileDetails h1')
            if title:
                name = title.text.strip() or name
        except:
            pass

        print(f"Found: {name}")

        confirm = get_input(f"\nAdd '{name}' to farm list? (y/n): ")
        if confirm.lower() == 'y':
            troops = None
            use_default = get_input("Use default troops? (y/n): ")
            if use_default.lower() != 'y':
                troops = self.configure_troops()

            self.farming.add_farm(name, x, y, troops)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def configure_troops(self, show_tribe: bool = True) -> Dict[str, int]:
        """Configure troops for a farm"""
        print(f"\n{Colors.YELLOW}Configure troops to send:{Colors.END}")
        print("Enter troop amounts (0 or blank to skip):\n")

        troops = {}

        # Tribe-specific troop names
        tribe = self.farming.tribe if hasattr(self.farming, 'tribe') else 'romans'

        tribe_troops = {
            'romans': [
                ('t1', 'Legionnaire'),
                ('t2', 'Praetorian'),
                ('t3', 'Imperian'),
                ('t4', 'Equites Legati'),
                ('t5', 'Equites Imperatoris'),
                ('t6', 'Equites Caesaris'),
            ],
            'gauls': [
                ('t1', 'Phalanx'),
                ('t2', 'Swordsman'),
                ('t3', 'Pathfinder'),
                ('t4', 'Theutates Thunder'),
                ('t5', 'Druidrider'),
                ('t6', 'Haeduan'),
            ],
            'teutons': [
                ('t1', 'Clubswinger'),
                ('t2', 'Spearfighter'),
                ('t3', 'Axefighter'),
                ('t4', 'Scout'),
                ('t5', 'Paladin'),
                ('t6', 'Teutonic Knight'),
            ],
        }

        troop_types = tribe_troops.get(tribe, tribe_troops['romans'])

        if show_tribe:
            print(f"  {Colors.CYAN}Tribe: {tribe.capitalize()}{Colors.END}\n")

        for troop_id, troop_name in troop_types:
            amount = get_input(f"  {troop_name} ({troop_id}): ")
            try:
                amount = int(amount) if amount else 0
                if amount > 0:
                    troops[troop_id] = amount
            except ValueError:
                pass

        return troops

    def edit_farm_troops(self):
        """Edit troops for a specific farm"""
        clear_screen()
        print_header("EDIT FARM TROOPS")

        self.farming.print_farm_list()

        farm_id = get_input("\nEnter farm ID to edit: ")
        try:
            farm_id = int(farm_id)
            if farm_id not in self.farming.farms:
                print(f"{Colors.RED}Farm not found{Colors.END}")
            else:
                farm = self.farming.farms[farm_id]
                print(f"\n{Colors.YELLOW}Editing troops for: {farm.name}{Colors.END}")
                print(f"Current troops: {farm.troops}")

                troops = self.configure_troops()
                self.farming.update_farm_troops(farm_id, troops)
                print(f"{Colors.GREEN}✓ Troops updated{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid ID{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def toggle_farm(self):
        """Toggle farm enabled/disabled"""
        clear_screen()
        print_header("TOGGLE FARM")

        self.farming.print_farm_list()

        farm_id = get_input("\nEnter farm ID to toggle: ")
        try:
            farm_id = int(farm_id)
            if self.farming.toggle_farm(farm_id):
                status = "enabled" if self.farming.farms[farm_id].enabled else "disabled"
                print(f"{Colors.GREEN}✓ Farm {farm_id} is now {status}{Colors.END}")
            else:
                print(f"{Colors.RED}Farm not found{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid ID{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def remove_farm(self):
        """Remove a farm from the list"""
        clear_screen()
        print_header("REMOVE FARM")

        self.farming.print_farm_list()

        farm_id = get_input("\nEnter farm ID to remove: ")
        try:
            farm_id = int(farm_id)
            farm = self.farming.farms.get(farm_id)
            if farm:
                confirm = get_input(f"Remove '{farm.name}'? (y/n): ")
                if confirm.lower() == 'y':
                    self.farming.remove_farm(farm_id)
                    print(f"{Colors.GREEN}✓ Farm removed{Colors.END}")
            else:
                print(f"{Colors.RED}Farm not found{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid ID{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def set_default_troops(self):
        """Set default troops for new farms"""
        clear_screen()
        print_header("SET DEFAULT TROOPS")

        print(f"Current defaults: {self.farming.default_troops}\n")

        troops = self.configure_troops()
        self.farming.set_default_troops(troops)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def change_all_farm_troops(self):
        """Change troops for ALL farms at once"""
        clear_screen()
        print_header("CHANGE ALL FARM TROOPS")

        all_farms = self.farming.get_all_farms()
        if not all_farms:
            print(f"{Colors.RED}No farms in the list{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        enabled_farms = self.farming.get_enabled_farms()
        print(f"Total farms: {len(all_farms)} ({len(enabled_farms)} enabled)\n")

        # Show current troop configs
        print(f"{Colors.YELLOW}Current troop configurations:{Colors.END}")
        unique_configs = {}
        for farm in all_farms:
            config_str = str(sorted(farm.troops.items())) if farm.troops else "none"
            if config_str not in unique_configs:
                unique_configs[config_str] = []
            unique_configs[config_str].append(farm.name)

        for config, farms in unique_configs.items():
            print(f"  {config}: {len(farms)} farm(s)")

        print(f"\n{Colors.BOLD}Options:{Colors.END}")
        print(f"  1. Enter new troops manually")
        print(f"  2. Copy from a specific farm")
        print(f"  3. Quick set (e.g., '10 t3' for 10 of troop 3)")
        print(f"  4. Use default troops")
        print(f"  5. Clear all troops")
        print(f"  0. Cancel")

        choice = get_input("\nChoice: ")

        troops = None

        if choice == "0":
            return
        elif choice == "1":
            troops = self.configure_troops()
        elif choice == "2":
            self.farming.print_farm_list()
            farm_id = get_input("\nEnter farm ID to copy from: ")
            try:
                farm_id = int(farm_id)
                if farm_id in self.farming.farms:
                    troops = self.farming.farms[farm_id].troops.copy()
                    print(f"Copying troops: {troops}")
                else:
                    print(f"{Colors.RED}Farm not found{Colors.END}")
                    input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                    return
            except ValueError:
                print(f"{Colors.RED}Invalid ID{Colors.END}")
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return
        elif choice == "3":
            print(f"\n{Colors.YELLOW}Quick set format: <amount> <troop_id>{Colors.END}")
            print(f"Examples: '10 t3', '5 t1', '20 t4 10 t5'")
            quick = get_input("Enter: ")
            troops = {}
            parts = quick.split()
            i = 0
            while i < len(parts) - 1:
                try:
                    amount = int(parts[i])
                    troop_id = parts[i + 1].lower()
                    if troop_id.startswith('t') and troop_id[1:].isdigit():
                        troops[troop_id] = amount
                    i += 2
                except (ValueError, IndexError):
                    i += 1
            if troops:
                print(f"Parsed: {troops}")
            else:
                print(f"{Colors.RED}Could not parse troops{Colors.END}")
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return
        elif choice == "4":
            troops = self.farming.default_troops.copy()
            if not troops:
                print(f"{Colors.RED}No default troops set. Use option 7 in Farming menu first.{Colors.END}")
                input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
                return
            print(f"Using default troops: {troops}")
        elif choice == "5":
            troops = {}
            print("Clearing all troops")
        else:
            return

        if troops is None:
            return

        # Choose which farms to update
        print(f"\n{Colors.BOLD}Apply to:{Colors.END}")
        print(f"  1. ALL farms ({len(all_farms)})")
        print(f"  2. Only ENABLED farms ({len(enabled_farms)})")
        print(f"  0. Cancel")

        apply_choice = get_input("\nChoice: ")

        if apply_choice == "1":
            farms_to_update = all_farms
        elif apply_choice == "2":
            farms_to_update = enabled_farms
        else:
            return

        confirm = get_input(f"\nSet {troops} on {len(farms_to_update)} farms? (y/n): ")
        if confirm.lower() != 'y':
            return

        for farm in farms_to_update:
            self.farming.update_farm_troops(farm.id, troops.copy())

        print(f"{Colors.GREEN}✓ Updated troops for {len(farms_to_update)} farm(s){Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def send_all_raids(self):
        """Send raids to all enabled farms"""
        clear_screen()
        print_header("SEND ALL RAIDS")

        enabled = self.farming.get_enabled_farms()
        if not enabled:
            print(f"{Colors.RED}No enabled farms in the list{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"Will send raids to {len(enabled)} farm(s):\n")
        for farm in enabled:
            print(f"  - {farm.name} ({farm.x}|{farm.y})")

        confirm = get_input(f"\n{Colors.YELLOW}Send raids now? (y/n): {Colors.END}")
        if confirm.lower() == 'y':
            self.farming.send_all_raids()

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def auto_farm_continuous(self):
        """Continuously send raids automatically"""
        clear_screen()
        print_header("AUTO FARM")

        enabled = self.farming.get_enabled_farms()
        if not enabled:
            print(f"{Colors.RED}No enabled farms in the list{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}This will continuously send raids to {len(enabled)} farm(s).{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        interval = get_input(f"Raid interval in seconds (default {self.farming.raid_interval}): ")
        try:
            interval = int(interval) if interval else self.farming.raid_interval
        except ValueError:
            interval = self.farming.raid_interval

        confirm = get_input(f"\nStart auto-farming every {interval}s? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        self._run_auto_farm_loop(interval, stop_flag)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _run_auto_farm_loop(self, interval: int, stop_flag: StopFlag):
        """The actual auto-farm loop"""
        print(f"\n{Colors.GREEN}Starting auto-farm...{Colors.END}")
        print(f"Interval: {interval}s")
        print(f"\n{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        # Start key listener thread
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_raids = 0
        cycles = 0

        try:
            while not stop_flag.should_stop():
                cycles += 1
                print(f"\n{Colors.CYAN}--- Raid Cycle {cycles} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")

                results = self.farming.send_all_raids()
                total_raids += results['sent']

                print(f"Total raids sent: {total_raids}")
                print(f"{Colors.RED}[Q/S=stop]{Colors.END}")

                if stop_flag.should_stop():
                    break

                # Wait with periodic stop checks
                print(f"Next raid in {interval}s...")
                for _ in range(interval):
                    if stop_flag.should_stop():
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n\n{Colors.YELLOW}Auto-farm stopped{Colors.END}")
        print(f"\n{'='*50}")
        print(f"Total cycles: {cycles}")
        print(f"Total raids sent: {total_raids}")
        print(f"{'='*50}")
        self.logger.info(f"Auto-farm completed: {total_raids} raids in {cycles} cycles")

    def auto_raid_travel_time(self):
        """Auto-raid based on travel time — re-sends raids as troops return"""
        clear_screen()
        print_header("AUTO RAID (TRAVEL-TIME BASED)")

        enabled = self.farming.get_enabled_farms()
        if not enabled:
            print(f"{Colors.RED}No enabled farms in the list{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}This will send raids and automatically re-send when troops return.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q'/'S' to stop{Colors.END}\n")

        # Prompt for tribe and server speed if not set
        tribe = get_input(f"Your tribe (romans/gauls/teutons) [default: {self.farming.tribe}]: ")
        if tribe and tribe.lower() in ('romans', 'gauls', 'teutons'):
            self.farming.tribe = tribe.lower()

        speed = get_input(f"Server speed multiplier [default: {self.farming.server_speed}]: ")
        if speed:
            try:
                self.farming.server_speed = int(speed)
            except ValueError:
                pass

        home = get_input(f"Home village coords x|y [default: {self.farming.home_x}|{self.farming.home_y}]: ")
        if home and '|' in home:
            try:
                hx, hy = home.split('|')
                self.farming.home_x = int(hx.strip())
                self.farming.home_y = int(hy.strip())
            except ValueError:
                pass

        print(f"\nFarms to raid:")
        for farm in enabled:
            est = self.farming.estimate_travel_time(farm)
            est_str = f" (~{est}s round-trip)" if est > 0 else ""
            print(f"  - {farm.name} ({farm.x}|{farm.y}){est_str}")

        confirm = get_input(f"\nStart auto-raid? (y/n): ")
        if confirm.lower() != 'y':
            return

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Starting travel-time auto-raid...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        stats = self.farming.auto_raid_loop(stop_flag.should_stop)

        print(f"\n\n{Colors.YELLOW}Auto-raid stopped{Colors.END}")
        print(f"\n{'='*50}")
        print(f"Total raids sent: {stats['total_sent']}")
        print(f"Total failed: {stats['total_failed']}")
        print(f"{'='*50}")
        self.logger.info(f"Auto-raid completed: {stats['total_sent']} sent, {stats['total_failed']} failed")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def farm_statistics(self):
        """Show farm statistics"""
        clear_screen()
        print_header("FARM STATISTICS")

        farms = self.farming.get_all_farms()

        if not farms:
            print("No farms in the list")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        total_raids = sum(f.raids_sent for f in farms)
        enabled = len([f for f in farms if f.enabled])

        print(f"{Colors.BOLD}Overview:{Colors.END}")
        print(f"  Total farms: {len(farms)}")
        print(f"  Enabled farms: {enabled}")
        print(f"  Total raids sent: {total_raids}")
        print(f"  Default troops: {self.farming.default_troops}")
        print(f"  Raid interval: {self.farming.raid_interval}s")

        print(f"\n{Colors.BOLD}Top Farms by Raids:{Colors.END}")
        sorted_farms = sorted(farms, key=lambda f: f.raids_sent, reverse=True)[:10]
        for i, farm in enumerate(sorted_farms, 1):
            print(f"  {i}. {farm.name} ({farm.x}|{farm.y}): {farm.raids_sent} raids")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== FARM LIST MANAGEMENT ====================

    def view_all_farm_lists(self):
        """View all farm lists summary"""
        clear_screen()
        print_header("ALL FARM LISTS")
        self.farming.print_all_farm_lists()
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def create_farm_list(self):
        """Create a new named farm list"""
        clear_screen()
        print_header("CREATE FARM LIST")

        self.farming.print_all_farm_lists()

        name = get_input("\nNew list name: ")
        if not name:
            return

        print(f"\nSet default troops for this list?")
        print(f"  1. Use global defaults ({self.farming.default_troops})")
        print(f"  2. Configure new defaults")
        print(f"  0. Cancel")

        choice = get_input("\nChoice: ")
        if choice == "0":
            return
        elif choice == "2":
            troops = self.configure_troops()
            self.farming.create_farm_list(name, troops)
        else:
            self.farming.create_farm_list(name)

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def switch_farm_list(self):
        """Switch the active farm list"""
        clear_screen()
        print_header("SWITCH ACTIVE FARM LIST")

        self.farming.print_all_farm_lists()

        names = self.farming.get_farm_list_names()
        if len(names) <= 1:
            print(f"\n{Colors.YELLOW}Only one list exists. Create more lists first.{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"\nAvailable lists:")
        for i, name in enumerate(names, 1):
            active = " (active)" if name == self.farming.active_list_name else ""
            count = len(self.farming.farm_lists[name].farms)
            print(f"  {i}. {name} ({count} farms){active}")

        choice = get_input("\nSelect list number: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(names):
                self.farming.switch_active_list(names[idx])
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            # Try by name
            if choice in names:
                self.farming.switch_active_list(choice)
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def delete_farm_list(self):
        """Delete a farm list"""
        clear_screen()
        print_header("DELETE FARM LIST")

        self.farming.print_all_farm_lists()

        names = self.farming.get_farm_list_names()
        non_active = [n for n in names if n != self.farming.active_list_name]

        if not non_active:
            print(f"\n{Colors.YELLOW}Cannot delete the only/active list. Switch first.{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"\nDeletable lists (cannot delete active list '{self.farming.active_list_name}'):")
        for i, name in enumerate(non_active, 1):
            count = len(self.farming.farm_lists[name].farms)
            print(f"  {i}. {name} ({count} farms)")

        choice = get_input("\nSelect list number to delete: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(non_active):
                name = non_active[idx]
                count = len(self.farming.farm_lists[name].farms)
                confirm = get_input(f"Delete '{name}' with {count} farms? (y/n): ")
                if confirm.lower() == 'y':
                    self.farming.delete_farm_list(name)
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid selection{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def move_farm_to_list(self):
        """Move a farm from one list to another"""
        clear_screen()
        print_header("MOVE FARM TO ANOTHER LIST")

        names = self.farming.get_farm_list_names()
        if len(names) < 2:
            print(f"{Colors.YELLOW}Need at least 2 farm lists. Create another list first.{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Show current active list farms
        self.farming.print_farm_list()

        farm_id = get_input("\nEnter farm ID to move: ")
        try:
            farm_id = int(farm_id)
        except ValueError:
            print(f"{Colors.RED}Invalid ID{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        if farm_id not in self.farming.farms:
            print(f"{Colors.RED}Farm #{farm_id} not found in active list{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Show target lists
        other_lists = [n for n in names if n != self.farming.active_list_name]
        print(f"\nMove to which list?")
        for i, name in enumerate(other_lists, 1):
            count = len(self.farming.farm_lists[name].farms)
            print(f"  {i}. {name} ({count} farms)")

        choice = get_input("\nSelect target list: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(other_lists):
                self.farming.move_farm_to_list(farm_id, self.farming.active_list_name, other_lists[idx])
            else:
                print(f"{Colors.RED}Invalid selection{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid selection{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== FARM FINDER ====================

    def scan_for_farms(self):
        """Scan map area for farms and auto-add to a list"""
        clear_screen()
        print_header("FARM FINDER - AUTO SCAN")

        # Center coordinates
        default_x = self.farming.home_x
        default_y = self.farming.home_y
        print(f"Center coordinates (default: home {default_x}|{default_y})")
        coords = get_input(f"Center x|y [{default_x}|{default_y}]: ")
        if coords and '|' in coords:
            try:
                cx, cy = coords.split('|')
                default_x = int(cx.strip())
                default_y = int(cy.strip())
            except ValueError:
                print(f"{Colors.RED}Invalid coordinates, using home{Colors.END}")

        # Radius
        radius_str = get_input("Scan radius [10]: ")
        try:
            radius = int(radius_str) if radius_str else 10
        except ValueError:
            radius = 10

        # Estimate
        tile_count, est_seconds = self.farm_finder.estimate_scan_time(radius)
        est_min = est_seconds // 60
        est_sec = est_seconds % 60
        print(f"\n  Estimated: {tile_count} tiles, ~{est_min}m {est_sec}s")

        # Max population
        max_pop_str = get_input("Max population [50]: ")
        try:
            max_pop = int(max_pop_str) if max_pop_str else 50
        except ValueError:
            max_pop = 50

        # Filter options
        print(f"\n{Colors.YELLOW}Include in scan:{Colors.END}")
        inc_natars = get_input("  Include Natars? (y/n) [y]: ")
        inc_villages = get_input("  Include player villages? (y/n) [y]: ")
        inc_unocc_oasis = get_input("  Include unoccupied oases? (y/n) [y]: ")
        inc_occ_oasis = get_input("  Include occupied oases? (y/n) [y]: ")

        exclude_alliances_str = get_input("  Exclude alliances (comma-separated, or Enter to skip): ")
        exclude_players_str = get_input("  Exclude players (comma-separated, or Enter to skip): ")

        scan_filter = ScanFilter(
            radius=radius,
            max_population=max_pop,
            include_natars=inc_natars.lower() != 'n',
            include_player_villages=inc_villages.lower() != 'n',
            include_unoccupied_oases=inc_unocc_oasis.lower() != 'n',
            include_occupied_oases=inc_occ_oasis.lower() != 'n',
            exclude_alliances=[a.strip() for a in exclude_alliances_str.split(',') if a.strip()] if exclude_alliances_str else [],
            exclude_players=[p.strip() for p in exclude_players_str.split(',') if p.strip()] if exclude_players_str else [],
        )

        # Target list selection
        names = self.farming.get_farm_list_names()
        print(f"\n{Colors.YELLOW}Add found farms to which list?{Colors.END}")
        for i, name in enumerate(names, 1):
            active = " (active)" if name == self.farming.active_list_name else ""
            count = len(self.farming.farm_lists[name].farms)
            print(f"  {i}. {name} ({count} farms){active}")
        print(f"  {len(names) + 1}. Create new list")

        list_choice = get_input(f"\nSelect list [{self.farming.active_list_name}]: ")
        target_list = self.farming.active_list_name

        if list_choice:
            try:
                idx = int(list_choice) - 1
                if idx == len(names):
                    # Create new list
                    new_name = get_input("New list name: ")
                    if new_name:
                        self.farming.create_farm_list(new_name)
                        target_list = new_name
                elif 0 <= idx < len(names):
                    target_list = names[idx]
            except ValueError:
                if list_choice in names:
                    target_list = list_choice

        # Confirmation
        print(f"\n{Colors.BOLD}Scan Summary:{Colors.END}")
        print(f"  Center: ({default_x}|{default_y})")
        print(f"  Radius: {radius}")
        print(f"  Tiles: ~{tile_count}")
        print(f"  Max pop: {max_pop}")
        print(f"  Target list: {target_list}")

        confirm = get_input(f"\n{Colors.YELLOW}Start scan? (y/n): {Colors.END}")
        if confirm.lower() != 'y':
            return

        # Run scan with stop flag
        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        print(f"\n{Colors.GREEN}Starting farm finder scan...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q'/'S' to stop <<<{Colors.END}")
        print("=" * 50)

        stats = self.farm_finder.scan_area(
            center_x=default_x,
            center_y=default_y,
            scan_filter=scan_filter,
            target_list=target_list,
            stop_callback=stop_flag.should_stop,
        )

        stop_flag.stop()

        self.logger.info(f"Farm finder scan: {stats['added']} farms added from {stats['scanned']} tiles scanned")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def clear_scan_history(self):
        """Clear farm finder scan history"""
        clear_screen()
        print_header("CLEAR SCAN HISTORY")

        count = len(self.farming.scan_history.get('scanned_coords', []))
        print(f"Scan history contains {count} scanned coordinates.")
        print(f"Clearing allows re-scanning previously visited tiles.\n")

        confirm = get_input(f"Clear scan history? (y/n): ")
        if confirm.lower() == 'y':
            self.farm_finder.clear_scan_history()

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== AI ASSISTANT ====================

    def ai_assistant_menu(self):
        """AI Assistant chat interface"""
        while True:
            clear_screen()
            print_header("AI ASSISTANT")

            print_menu("AI Options", [
                "🎮 Give command (e.g., 'upgrade barracks to level 10')",
                "Get strategic advice",
                "Analyze current page",
                "Ask a question",
                "Find element selector",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.ai_command()
            elif choice == "2":
                self.get_ai_strategy()
            elif choice == "3":
                self.ai_analyze_page()
            elif choice == "4":
                self.ai_ask_question()
            elif choice == "5":
                self.ai_find_selector()

    def ai_command(self):
        """Process natural language commands"""
        clear_screen()
        print_header("AI COMMAND")

        print(f"{Colors.CYAN}Examples:{Colors.END}")
        print("  - upgrade barracks to level 10")
        print("  - upgrade clay pit to 15")
        print("  - upgrade main building to level 20")
        print("  - upgrade cropland to 12")
        print()

        command = get_input("Your command: ").lower()

        if not command:
            return

        # Parse the command
        parsed = self.parse_upgrade_command(command)

        if not parsed:
            print(f"\n{Colors.RED}Could not understand command.{Colors.END}")
            print("Try: 'upgrade [building name] to level [number]'")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        building_name = parsed['building']
        target_level = parsed['level']

        print(f"\n{Colors.YELLOW}Searching for '{building_name}'...{Colors.END}")

        # Find the building
        matches = self.buildings.find_building_by_name(building_name)

        if not matches:
            print(f"\n{Colors.RED}No building found matching '{building_name}'{Colors.END}")
            print("\nAvailable buildings:")
            print("  Resources: Woodcutter, Clay Pit, Iron Mine, Cropland")
            print("  Village: Main Building, Barracks, Stable, Warehouse, Granary, etc.")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # If multiple matches, let user choose
        if len(matches) > 1:
            print(f"\n{Colors.YELLOW}Found {len(matches)} matching buildings:{Colors.END}\n")
            for i, m in enumerate(matches, 1):
                print(f"  {i}. {m['name']} (ID #{m['id']}) - Level {m['level']}")

            choice = get_input("\nWhich one? (number or 'all'): ")

            if choice.lower() == 'all':
                # Upgrade all matching buildings
                print(f"\n{Colors.GREEN}Upgrading ALL {len(matches)} '{building_name}' to level {target_level}{Colors.END}")
                confirm = get_input("Confirm? (y/n): ")
                if confirm.lower() != 'y':
                    return

                # Use stop flag for upgrades
                stop_flag = StopFlag()
                listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
                listener_thread.start()
                print(f"{Colors.RED}>>> Press Q/S to stop <<<{Colors.END}\n")

                for m in matches:
                    if stop_flag.should_stop():
                        break
                    self.buildings.upgrade_to_level(m['id'], target_level, stop_flag.should_stop)

            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(matches):
                        selected = matches[idx]
                        print(f"\n{Colors.GREEN}Upgrading {selected['name']} to level {target_level}{Colors.END}")
                        confirm = get_input("Confirm? (y/n): ")
                        if confirm.lower() == 'y':
                            stop_flag = StopFlag()
                            listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
                            listener_thread.start()
                            self.buildings.upgrade_to_level(selected['id'], target_level, stop_flag.should_stop)
                    else:
                        print(f"{Colors.RED}Invalid selection{Colors.END}")
                except ValueError:
                    print(f"{Colors.RED}Invalid input{Colors.END}")
        else:
            # Single match
            selected = matches[0]
            print(f"\n{Colors.GREEN}Found: {selected['name']} (ID #{selected['id']}) - Level {selected['level']}{Colors.END}")
            print(f"{Colors.GREEN}Target: Level {target_level}{Colors.END}")

            confirm = get_input("\nStart upgrade? (y/n): ")
            if confirm.lower() == 'y':
                stop_flag = StopFlag()
                listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
                listener_thread.start()
                result = self.buildings.upgrade_to_level(selected['id'], target_level, stop_flag.should_stop)
                self.logger.info(f"AI Command: {selected['name']} L{result['start_level']} -> L{result['final_level']}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def parse_upgrade_command(self, command: str) -> Optional[Dict]:
        """Parse natural language upgrade commands"""
        # Patterns to match
        # "upgrade X to level Y" or "upgrade X to Y"
        patterns = [
            r'upgrade\s+(.+?)\s+to\s+level\s+(\d+)',
            r'upgrade\s+(.+?)\s+to\s+(\d+)',
            r'level\s+up\s+(.+?)\s+to\s+(\d+)',
            r'build\s+(.+?)\s+to\s+level\s+(\d+)',
            r'build\s+(.+?)\s+to\s+(\d+)',
            r'(.+?)\s+to\s+level\s+(\d+)',
            r'(.+?)\s+to\s+(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                building = match.group(1).strip()
                level = int(match.group(2))

                # Clean up building name
                building = building.replace('the ', '').strip()

                return {'building': building, 'level': level}

        return None

    def get_ai_strategy(self):
        """Get AI strategic advice"""
        clear_screen()
        print_header("AI STRATEGY")

        self.session.navigate_to_village_overview()
        self.resources.update_resources()
        self.resources.update_production()

        game_data = {
            'resources': self.resources.resources,
            'production': self.resources.production,
            'storage_capacity': self.resources.storage_capacity,
        }

        print(f"{Colors.YELLOW}Analyzing game state...{Colors.END}\n")
        advice = self.healer.get_game_strategy(game_data)

        if advice:
            print(f"{Colors.GREEN}AI Advice:{Colors.END}\n")
            print(advice)
        else:
            print(f"{Colors.RED}Could not get AI advice{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def ai_analyze_page(self):
        """AI analyze current page"""
        clear_screen()
        print_header("AI PAGE ANALYSIS")

        self.browser.screenshot('ai_analyze.png')

        print(f"{Colors.YELLOW}Analyzing screenshot...{Colors.END}\n")
        analysis = self.healer.analyze_screenshot(
            'screenshots/ai_analyze.png',
            "Describe what's on this Travian game screen. What actions are available? List key elements and their purposes."
        )

        if analysis:
            print(analysis)
        else:
            print(f"{Colors.RED}Could not analyze page{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def ai_ask_question(self):
        """Ask AI a question"""
        clear_screen()
        print_header("ASK AI")

        question = get_input("Your question: ")

        if question:
            self.browser.screenshot('ai_question.png')

            print(f"\n{Colors.YELLOW}Thinking...{Colors.END}\n")
            answer = self.healer.analyze_screenshot(
                'screenshots/ai_question.png',
                f"Based on this Travian game screen, answer: {question}"
            )

            if answer:
                print(f"{Colors.GREEN}AI Response:{Colors.END}\n")
                print(answer)
            else:
                print(f"{Colors.RED}Could not get answer{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def ai_find_selector(self):
        """AI find element selector"""
        clear_screen()
        print_header("AI FIND SELECTOR")

        element_desc = get_input("Describe the element to find: ")

        if element_desc:
            print(f"\n{Colors.YELLOW}Analyzing page...{Colors.END}\n")
            result = self.healer.analyze_page_for_selector(element_desc, "unknown")

            if result:
                print(f"{Colors.GREEN}Found selectors:{Colors.END}")
                print(f"  Primary: {result.get('primary_selector', {})}")
                print(f"  Alternatives: {result.get('alternatives', [])}")
                print(f"  Explanation: {result.get('explanation', '')}")
            else:
                print(f"{Colors.RED}Could not find selector{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== SETTINGS ====================

    def settings_menu(self):
        """Settings menu"""
        while True:
            clear_screen()
            print_header("SETTINGS")

            print(f"{Colors.BOLD}Current Settings:{Colors.END}\n")
            for key, value in self.settings.items():
                status = f"{Colors.GREEN}ON{Colors.END}" if value is True else f"{Colors.RED}OFF{Colors.END}" if value is False else str(value)
                print(f"  {key}: {status}")

            print_menu("Settings Options", [
                "Toggle auto-upgrade",
                "Toggle auto-train",
                "Set upgrade priority",
                "Set check interval",
                "Toggle attack notifications",
                "Save settings",
                "Load settings",
                "Clear cache",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.settings['auto_upgrade'] = not self.settings['auto_upgrade']
            elif choice == "2":
                self.settings['auto_train'] = not self.settings['auto_train']
            elif choice == "3":
                self.set_priority()
            elif choice == "4":
                self.set_interval()
            elif choice == "5":
                self.settings['notify_attacks'] = not self.settings['notify_attacks']
            elif choice == "6":
                self.save_settings()
            elif choice == "7":
                self.load_settings()
            elif choice == "8":
                self.clear_all_cache()

    def set_priority(self):
        """Set upgrade priority"""
        print("\nPriority options: balanced, resources, military")
        priority = get_input("Enter priority: ")
        if priority in ['balanced', 'resources', 'military']:
            self.settings['upgrade_priority'] = priority
            print(f"{Colors.GREEN}✓ Priority set to {priority}{Colors.END}")
        else:
            print(f"{Colors.RED}Invalid priority{Colors.END}")

    def set_interval(self):
        """Set check interval"""
        interval = get_input("Check interval in seconds (30-600): ")
        try:
            val = int(interval)
            if 30 <= val <= 600:
                self.settings['check_interval'] = val
                print(f"{Colors.GREEN}✓ Interval set to {val}s{Colors.END}")
            else:
                print(f"{Colors.RED}Value out of range{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Invalid number{Colors.END}")

    def save_settings(self):
        """Save settings to file"""
        try:
            with open('bot_settings.json', 'w') as f:
                json.dump(self.settings, f, indent=2)
            print(f"{Colors.GREEN}✓ Settings saved{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}✗ Could not save: {e}{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def load_settings(self):
        """Load settings from file"""
        try:
            with open('bot_settings.json', 'r') as f:
                self.settings = json.load(f)
            print(f"{Colors.GREEN}✓ Settings loaded{Colors.END}")
        except FileNotFoundError:
            print(f"{Colors.YELLOW}No settings file found{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}✗ Could not load: {e}{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def clear_all_cache(self):
        """Clear all cache files"""
        import shutil

        # Define cache files and directories
        cache_files = [
            'farm_list.json',
            'village_cache.json',
            'village_training.json',
            'bot_settings.json',
        ]
        cache_dirs = [
            'session_data',
            'screenshots',
            'logs',
        ]

        print(f"\n{Colors.YELLOW}Cache files that will be deleted:{Colors.END}")
        for f in cache_files:
            exists = os.path.exists(f)
            status = f"{Colors.GREEN}exists{Colors.END}" if exists else f"{Colors.RED}not found{Colors.END}"
            print(f"  - {f}: {status}")

        print(f"\n{Colors.YELLOW}Cache directories that will be cleared:{Colors.END}")
        for d in cache_dirs:
            exists = os.path.isdir(d)
            status = f"{Colors.GREEN}exists{Colors.END}" if exists else f"{Colors.RED}not found{Colors.END}"
            print(f"  - {d}/: {status}")

        print(f"\n{Colors.BOLD}Select what to clear:{Colors.END}")
        print(f"  1. All cache (files + directories)")
        print(f"  2. Only JSON files (farm_list, village_cache, etc.)")
        print(f"  3. Only session data (requires re-login)")
        print(f"  4. Only screenshots and logs")
        print(f"  0. Cancel")

        choice = get_input("\nChoice: ")

        if choice == "0":
            print(f"{Colors.YELLOW}Cancelled{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        deleted_count = 0

        if choice in ["1", "2"]:
            # Delete JSON files
            for f in cache_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                        print(f"  {Colors.GREEN}✓ Deleted {f}{Colors.END}")
                        deleted_count += 1
                except Exception as e:
                    print(f"  {Colors.RED}✗ Could not delete {f}: {e}{Colors.END}")

        if choice in ["1", "3"]:
            # Clear session_data
            if os.path.isdir('session_data'):
                try:
                    shutil.rmtree('session_data')
                    print(f"  {Colors.GREEN}✓ Deleted session_data/{Colors.END}")
                    deleted_count += 1
                except Exception as e:
                    print(f"  {Colors.RED}✗ Could not delete session_data: {e}{Colors.END}")

        if choice in ["1", "4"]:
            # Clear screenshots and logs
            for d in ['screenshots', 'logs']:
                if os.path.isdir(d):
                    try:
                        shutil.rmtree(d)
                        print(f"  {Colors.GREEN}✓ Deleted {d}/{Colors.END}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"  {Colors.RED}✗ Could not delete {d}: {e}{Colors.END}")

        # Reload farming module if farms were cleared
        if choice in ["1", "2"] and hasattr(self, 'farming'):
            self.farming.farms = {}
            self.farming.farm_counter = 0

        # Clear village map cache in memory
        if choice in ["1", "2"] and hasattr(self, 'village_map'):
            self.village_map.villages = {}

        print(f"\n{Colors.GREEN}✓ Cleared {deleted_count} items{Colors.END}")
        if choice in ["1", "3"]:
            print(f"{Colors.YELLOW}Note: You will need to re-login after clearing session data{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== REPORTS MANAGER ====================

    def reports_menu(self):
        """Reports management menu"""
        while True:
            clear_screen()
            print_header("REPORTS MANAGER")

            print_menu("Report Options", [
                "📊 Preview reports (count by category)",
                "🟢 Delete successful raids (no losses)",
                "🟡 Delete successful raids (with losses)",
                "🟢🟡 Delete ALL successful raids",
                "🔴 Delete defeats (unsuccessful attacks)",
                "🔵 Delete scout reports",
                "🗑️  Delete ALL reports on page",
                "🎯 Custom delete (select categories)",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.preview_reports()
            elif choice == "2":
                self.delete_reports_by_type(['success_no_loss'])
            elif choice == "3":
                self.delete_reports_by_type(['success_with_loss'])
            elif choice == "4":
                self.delete_reports_by_type(['success_no_loss', 'success_with_loss'])
            elif choice == "5":
                self.delete_reports_by_type(['defeat'])
            elif choice == "6":
                self.delete_reports_by_type(['scout'])
            elif choice == "7":
                self.delete_all_reports()
            elif choice == "8":
                self.custom_delete_reports()

    def preview_reports(self):
        """Navigate to reports and show count by category"""
        clear_screen()
        print_header("REPORT PREVIEW")

        print(f"{Colors.YELLOW}Scanning reports page...{Colors.END}\n")

        counts = self.reports.count_reports_by_category()

        total = sum(counts.values())
        if total == 0:
            print(f"{Colors.YELLOW}No reports found on current page (or page could not be parsed){Colors.END}")
        else:
            print(f"{'Category':<40} {'Count':>6}")
            print("-" * 48)
            for outcome, label in OUTCOME_LABELS.items():
                count = counts.get(outcome, 0)
                if count > 0:
                    color = {
                        'success_no_loss': Colors.GREEN,
                        'success_with_loss': Colors.YELLOW,
                        'defeat': Colors.RED,
                        'scout': Colors.CYAN,
                        'unknown': Colors.END,
                    }.get(outcome, Colors.END)
                    print(f"  {color}{label:<38}{Colors.END} {count:>6}")
                else:
                    print(f"  {label:<38} {count:>6}")
            print("-" * 48)
            print(f"  {'Total':<38} {total:>6}")
            print(f"\n{Colors.YELLOW}Note: Counts are for the current page only{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def delete_reports_by_type(self, categories: List[str]):
        """Delete reports of specified categories with confirmation"""
        clear_screen()
        print_header("DELETE REPORTS")

        labels = [OUTCOME_LABELS.get(c, c) for c in categories]
        print(f"Will delete: {Colors.YELLOW}{', '.join(labels)}{Colors.END}\n")

        confirm = get_input("Proceed with deletion? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        # Set up stop flag for interruptible operation
        stop_flag = StopFlag()
        listener = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener.start()

        print(f"\n{Colors.YELLOW}Deleting reports... (press Q to stop){Colors.END}\n")

        stats = self.reports.delete_reports_by_category(
            categories=categories,
            stop_callback=stop_flag.should_stop,
        )

        stop_flag.stop()

        print(f"\n{Colors.GREEN}Done! Deleted {stats['deleted']} reports across {stats['pages_processed']} page(s){Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def delete_all_reports(self):
        """Delete all reports on the current page"""
        clear_screen()
        print_header("DELETE ALL REPORTS")

        print(f"{Colors.RED}This will delete ALL reports on the current reports page!{Colors.END}\n")

        confirm = get_input("Are you sure? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        stop_flag = StopFlag()
        listener = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener.start()

        print(f"\n{Colors.YELLOW}Deleting all reports... (press Q to stop){Colors.END}\n")

        deleted = self.reports.delete_all_on_page(stop_callback=stop_flag.should_stop)

        stop_flag.stop()

        print(f"\n{Colors.GREEN}Done! Deleted {deleted} reports{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def custom_delete_reports(self):
        """Let user pick which categories to delete"""
        clear_screen()
        print_header("CUSTOM DELETE")

        print("Select categories to delete:\n")

        all_categories = list(OUTCOME_LABELS.keys())
        for i, cat in enumerate(all_categories, 1):
            print(f"  {Colors.CYAN}{i}.{Colors.END} {OUTCOME_LABELS[cat]}")
        print()

        selection = get_input("Enter numbers separated by commas (e.g. 1,3,4): ")
        if not selection:
            return

        selected = []
        try:
            for num in selection.split(','):
                idx = int(num.strip()) - 1
                if 0 <= idx < len(all_categories):
                    selected.append(all_categories[idx])
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        if not selected:
            print("No categories selected")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        self.delete_reports_by_type(selected)

    # ==================== AUTO MODE ====================

    def auto_mode_menu(self):
        """Auto mode - runs actions automatically"""
        clear_screen()
        print_header("AUTO MODE")

        print(f"Auto mode will run these actions every {self.settings['check_interval']}s:")
        print(f"  - Update resources: Always")
        print(f"  - Auto upgrade: {'Yes' if self.settings['auto_upgrade'] else 'No'}")
        print(f"  - Auto train: {'Yes' if self.settings['auto_train'] else 'No'}")
        print(f"  - Check attacks: {'Yes' if self.settings['notify_attacks'] else 'No'}")

        confirm = get_input("\nStart auto mode? (y/n): ")

        if confirm.lower() == 'y':
            self.run_auto_mode()

    def run_auto_mode(self):
        """Run bot in automatic mode with connection resilience"""
        print(f"\n{Colors.GREEN}Starting auto mode...{Colors.END}")
        print(f"{Colors.RED}>>> Press 'Q' or 'S' to stop <<<{Colors.END}\n")
        self.logger.info("Auto mode started")

        self.auto_mode = True
        cycle = 0
        consecutive_errors = 0
        max_consecutive_errors = 5

        # Start key listener thread
        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        try:
            while not stop_flag.should_stop():
                cycle += 1
                actions_taken = []
                print(f"\n{Colors.CYAN}--- Cycle {cycle} @ {datetime.now().strftime('%H:%M:%S')} ---{Colors.END}")
                self.logger.info(f"Auto mode cycle #{cycle} started")

                try:
                    # Update status
                    self.session.navigate_to_village_overview()
                    self.resources.update_resources()
                    self.resources.update_production()
                    actions_taken.append("status_update")

                    # Log resources
                    self.action_log.log_resources(
                        self.resources.resources,
                        self.resources.production
                    )

                    print(f"Resources: {self.resources.format_resources()}")

                    # Auto actions
                    if self.settings['auto_upgrade'] and not stop_flag.should_stop():
                        result = self.buildings.auto_upgrade_resources(self.session)
                        if result:
                            actions_taken.append("upgrade")
                            self.logger.info("Auto-upgrade performed")

                        if result:
                            actions_taken.append("train")
                            self.logger.info("Auto-train performed")

                    if self.settings['notify_attacks'] and not stop_flag.should_stop():
                        incoming = self.military.check_incoming_attacks()
                        if incoming:
                            print(f"{Colors.RED}⚠️  INCOMING ATTACKS: {len(incoming)}{Colors.END}")
                            self.logger.warning(f"Incoming attacks detected: {len(incoming)}")
                            for attack in incoming:
                                self.action_log.log_incoming_attack(
                                    attack.get('attacker', 'Unknown'),
                                    attack.get('arrival_time', 'Unknown')
                                )
                            actions_taken.append("attack_detected")

                    # Log cycle
                    self.action_log.log_cycle(cycle, actions_taken)

                    # Reset error counter on successful cycle
                    consecutive_errors = 0

                except Exception as e:
                    if is_connection_error(e):
                        consecutive_errors += 1
                        print(f"\n{Colors.RED}⚠️  Connection error in cycle {cycle}: {str(e)[:80]}{Colors.END}")
                        self.logger.warning(f"Connection error: {e}")

                        if consecutive_errors >= max_consecutive_errors:
                            print(f"{Colors.YELLOW}Too many consecutive errors, waiting for connection...{Colors.END}")

                        # Wait for connection to be restored
                        if self.wait_for_connection(stop_flag):
                            print(f"{Colors.GREEN}Connection restored, resuming auto mode...{Colors.END}")
                            continue
                        else:
                            print(f"{Colors.RED}Could not restore connection{Colors.END}")
                            break
                    else:
                        # Non-connection error, log and continue
                        print(f"{Colors.RED}Error in cycle {cycle}: {e}{Colors.END}")
                        self.logger.error(f"Cycle error: {e}")
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"{Colors.RED}Too many consecutive errors, stopping{Colors.END}")
                            break

                print(f"{Colors.RED}[Press Q/S to stop]{Colors.END}")

                # Wait with periodic stop checks
                for _ in range(self.settings['check_interval']):
                    if stop_flag.should_stop():
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()

        self.auto_mode = False
        print(f"\n{Colors.YELLOW}Auto mode stopped{Colors.END}")
        self.logger.info(f"Auto mode stopped after {cycle} cycles")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== AI AUTO-PILOT ====================

    def autopilot_menu(self):
        """AI Auto-Pilot - fully automated with AI oversight"""
        clear_screen()
        print_header("🤖 AI AUTO-PILOT MODE")

        print(f"""{Colors.YELLOW}
AI Auto-Pilot will automatically manage your account:

  🏗️  Buildings    - Upgrade resources & village buildings
  ⚔️  Military     - Train troops in all villages
  🌾 Farming      - Send raids to all farms
  🛡️  Defense      - Monitor for incoming attacks
  📊 Analysis     - AI analyzes & optimizes strategy

The AI will make decisions based on current game state,
prioritize actions, and handle unexpected situations.
{Colors.END}""")

        print(f"\n{Colors.BOLD}Current Configuration:{Colors.END}")

        # Show what's configured
        village_configs = self.military.load_village_training_configs()
        farm_count = len(self.farming.get_enabled_farms())

        print(f"  Villages configured for training: {len(village_configs)}")
        print(f"  Farms configured: {farm_count}")
        print(f"  AI API: {'✓ Available' if self._has_ai() else '✗ Not configured'}")

        print_menu("Auto-Pilot Options", [
            "🚀 START AUTO-PILOT (Full AI Control)",
            "⚙️  Configure Auto-Pilot Settings",
            "📋 View Auto-Pilot Status",
            "🧪 Run AI Analysis (one-time)",
        ])

        choice = get_input()

        if choice == "1":
            self.start_autopilot()
        elif choice == "2":
            self.configure_autopilot()
        elif choice == "3":
            self.view_autopilot_status()
        elif choice == "4":
            self.run_ai_analysis()

    def _has_ai(self) -> bool:
        """Check if AI (Claude) is available"""
        try:
            import anthropic
            return bool(config.anthropic_api_key)
        except ImportError:
            return False

    def configure_autopilot(self):
        """Configure auto-pilot settings"""
        clear_screen()
        print_header("AUTO-PILOT CONFIGURATION")

        # Initialize autopilot settings if not exists
        if not hasattr(self, 'autopilot_settings'):
            self.autopilot_settings = {
                'upgrade_resources': True,
                'upgrade_buildings': True,
                'train_troops': True,
                'send_farms': True,
                'check_attacks': True,
                'ai_decisions': True,
                'cycle_interval': 120,  # seconds between cycles
                'farm_interval': 300,   # seconds between farm raids
                'priority': 'balanced',  # balanced, economy, military
            }

        print(f"{Colors.BOLD}Current Settings:{Colors.END}\n")
        print(f"  1. Upgrade resources:    {'✓ ON' if self.autopilot_settings['upgrade_resources'] else '✗ OFF'}")
        print(f"  2. Upgrade buildings:    {'✓ ON' if self.autopilot_settings['upgrade_buildings'] else '✗ OFF'}")
        print(f"  3. Train troops:         {'✓ ON' if self.autopilot_settings['train_troops'] else '✗ OFF'}")
        print(f"  4. Send farm raids:      {'✓ ON' if self.autopilot_settings['send_farms'] else '✗ OFF'}")
        print(f"  5. Check attacks:        {'✓ ON' if self.autopilot_settings['check_attacks'] else '✗ OFF'}")
        print(f"  6. AI decisions:         {'✓ ON' if self.autopilot_settings['ai_decisions'] else '✗ OFF'}")
        print(f"  7. Cycle interval:       {self.autopilot_settings['cycle_interval']}s")
        print(f"  8. Farm interval:        {self.autopilot_settings['farm_interval']}s")
        print(f"  9. Priority:             {self.autopilot_settings['priority']}")
        print(f"\n  0. Back")

        choice = get_input("\nToggle setting (1-9): ")

        if choice == "1":
            self.autopilot_settings['upgrade_resources'] = not self.autopilot_settings['upgrade_resources']
        elif choice == "2":
            self.autopilot_settings['upgrade_buildings'] = not self.autopilot_settings['upgrade_buildings']
        elif choice == "3":
            self.autopilot_settings['train_troops'] = not self.autopilot_settings['train_troops']
        elif choice == "4":
            self.autopilot_settings['send_farms'] = not self.autopilot_settings['send_farms']
        elif choice == "5":
            self.autopilot_settings['check_attacks'] = not self.autopilot_settings['check_attacks']
        elif choice == "6":
            self.autopilot_settings['ai_decisions'] = not self.autopilot_settings['ai_decisions']
        elif choice == "7":
            interval = get_input("Cycle interval in seconds: ")
            try:
                self.autopilot_settings['cycle_interval'] = int(interval)
            except ValueError:
                pass
        elif choice == "8":
            interval = get_input("Farm interval in seconds: ")
            try:
                self.autopilot_settings['farm_interval'] = int(interval)
            except ValueError:
                pass
        elif choice == "9":
            print("\nPriority modes:")
            print("  1. balanced - Equal focus on everything")
            print("  2. economy  - Focus on resource production")
            print("  3. military - Focus on troop training")
            p = get_input("Choose priority: ")
            if p == "1":
                self.autopilot_settings['priority'] = 'balanced'
            elif p == "2":
                self.autopilot_settings['priority'] = 'economy'
            elif p == "3":
                self.autopilot_settings['priority'] = 'military'

        if choice != "0":
            self.configure_autopilot()  # Show menu again

    def view_autopilot_status(self):
        """View current autopilot status and statistics"""
        clear_screen()
        print_header("AUTO-PILOT STATUS")

        # Get current game state
        self.session.navigate_to_village_overview()
        self.resources.update_resources()

        print(f"{Colors.BOLD}Current Game State:{Colors.END}\n")
        print(f"  Resources: {self.resources.format_resources()}")
        print(f"  Free Crop: {self.resources.free_crop}")

        # Villages
        villages = self.village_cycler.get_all_villages()
        print(f"\n  Villages: {len(villages)}")
        for v in villages[:5]:  # Show first 5
            print(f"    - {v['name']}")

        # Training configs
        configs = self.military.load_village_training_configs()
        print(f"\n  Training configured: {len(configs)} village(s)")

        # Farms
        farms = self.farming.get_all_farms()
        enabled_farms = self.farming.get_enabled_farms()
        total_raids = sum(f.raids_sent for f in farms)
        print(f"\n  Farms: {len(enabled_farms)}/{len(farms)} enabled")
        print(f"  Total raids sent: {total_raids}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def run_ai_analysis(self):
        """Run a one-time AI analysis of current game state"""
        clear_screen()
        print_header("AI GAME ANALYSIS")

        if not self._has_ai():
            print(f"{Colors.RED}AI not available. Set ANTHROPIC_API_KEY in config.{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"{Colors.YELLOW}Gathering game data...{Colors.END}\n")

        # Collect game state
        self.session.navigate_to_village_overview()
        self.resources.update_resources()

        game_state = {
            'resources': self.resources.resources,
            'production': self.resources.production,
            'storage': self.resources.storage_capacity,
            'free_crop': self.resources.free_crop,
            'villages': len(self.village_cycler.get_all_villages()),
            'training_configs': len(self.military.load_village_training_configs()),
            'farms_enabled': len(self.farming.get_enabled_farms()),
            'total_farms': len(self.farming.get_all_farms()),
        }

        print(f"{Colors.YELLOW}Asking AI for analysis...{Colors.END}\n")

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.anthropic_api_key)

            prompt = f"""Analyze this Travian game state and provide strategic advice:

Game State:
- Resources: Wood={game_state['resources']['wood']}, Clay={game_state['resources']['clay']}, Iron={game_state['resources']['iron']}, Crop={game_state['resources']['crop']}
- Production/hour: Wood={game_state['production']['wood']}, Clay={game_state['production']['clay']}, Iron={game_state['production']['iron']}, Crop={game_state['production']['crop']}
- Storage Capacity: Wood={game_state['storage']['wood']}, Clay={game_state['storage']['clay']}, Iron={game_state['storage']['iron']}, Crop={game_state['storage']['crop']}
- Free Crop: {game_state['free_crop']}
- Villages: {game_state['villages']}
- Training configured for: {game_state['training_configs']} villages
- Farms: {game_state['farms_enabled']}/{game_state['total_farms']} enabled

Provide:
1. Overall assessment (1-2 sentences)
2. Top 3 priorities right now
3. Potential issues to watch
4. Recommended next actions

Keep response concise and actionable."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            print(f"{Colors.GREEN}AI Analysis:{Colors.END}\n")
            print(response.content[0].text)

        except Exception as e:
            print(f"{Colors.RED}AI Error: {e}{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def start_autopilot(self):
        """Start the full AI auto-pilot mode"""
        clear_screen()
        print_header("🚀 STARTING AI AUTO-PILOT")

        # Initialize settings if not exists
        if not hasattr(self, 'autopilot_settings'):
            self.autopilot_settings = {
                'upgrade_resources': True,
                'upgrade_buildings': True,
                'train_troops': True,
                'send_farms': True,
                'check_attacks': True,
                'ai_decisions': True,
                'cycle_interval': 120,
                'farm_interval': 300,
                'priority': 'balanced',
            }

        print(f"{Colors.YELLOW}Auto-Pilot Configuration:{Colors.END}")
        print(f"  Upgrade resources: {'✓' if self.autopilot_settings['upgrade_resources'] else '✗'}")
        print(f"  Upgrade buildings: {'✓' if self.autopilot_settings['upgrade_buildings'] else '✗'}")
        print(f"  Train troops:      {'✓' if self.autopilot_settings['train_troops'] else '✗'}")
        print(f"  Send farms:        {'✓' if self.autopilot_settings['send_farms'] else '✗'}")
        print(f"  AI decisions:      {'✓' if self.autopilot_settings['ai_decisions'] else '✗'}")
        print(f"  Cycle interval:    {self.autopilot_settings['cycle_interval']}s")
        print(f"  Priority:          {self.autopilot_settings['priority']}")

        print(f"\n{Colors.RED}>>> Press 'Q' or 'S' to stop Auto-Pilot <<<{Colors.END}\n")

        confirm = get_input("Start Auto-Pilot? (y/n): ")
        if confirm.lower() != 'y':
            return

        self._run_autopilot_loop()

    def _run_autopilot_loop(self):
        """Main auto-pilot execution loop with connection resilience"""
        print(f"\n{Colors.GREEN}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}   🤖 AI AUTO-PILOT ENGAGED{Colors.END}")
        print(f"{Colors.GREEN}{'='*60}{Colors.END}")

        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        cycle = 0
        last_farm_time = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        stats = {
            'upgrades': 0,
            'troops_trained': 0,
            'raids_sent': 0,
            'attacks_detected': 0,
            'ai_decisions': 0,
            'reconnections': 0,
        }

        # Load training configs once
        training_configs = self.military.load_village_training_configs()

        try:
            while not stop_flag.should_stop():
                cycle += 1
                cycle_start = time.time()

                print(f"\n{Colors.CYAN}{'─'*60}{Colors.END}")
                print(f"{Colors.CYAN}  CYCLE {cycle} @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
                print(f"{Colors.CYAN}{'─'*60}{Colors.END}")

                try:
                    # ===== 1. UPDATE STATUS =====
                    print(f"\n{Colors.BOLD}[1/6] 📊 Updating Status...{Colors.END}")
                    self.session.navigate_to_village_overview()
                    self.resources.update_resources()
                    print(f"      Resources: {self.resources.format_resources()}")
                    print(f"      Free Crop: {self.resources.free_crop}")

                    if stop_flag.should_stop():
                        break

                    # ===== 2. CHECK ATTACKS =====
                    if self.autopilot_settings['check_attacks']:
                        print(f"\n{Colors.BOLD}[2/6] 🛡️  Checking for Attacks...{Colors.END}")
                        incoming = self.military.check_incoming_attacks()
                        if incoming:
                            print(f"      {Colors.RED}⚠️  WARNING: {len(incoming)} INCOMING ATTACK(S)!{Colors.END}")
                            stats['attacks_detected'] += len(incoming)
                            # AI could decide what to do here
                        else:
                            print(f"      ✓ No incoming attacks")

                    if stop_flag.should_stop():
                        break

                    # ===== 3. UPGRADE RESOURCES =====
                    if self.autopilot_settings['upgrade_resources']:
                        print(f"\n{Colors.BOLD}[3/6] 🔨 Upgrading Resources...{Colors.END}")
                        upgraded = self._autopilot_upgrade_resources(stop_flag)
                        stats['upgrades'] += upgraded
                        print(f"      Upgraded {upgraded} field(s)")

                    if stop_flag.should_stop():
                        break

                    # ===== 4. UPGRADE BUILDINGS =====
                    if self.autopilot_settings['upgrade_buildings']:
                        print(f"\n{Colors.BOLD}[4/6] 🏗️  Upgrading Buildings...{Colors.END}")
                        upgraded = self._autopilot_upgrade_buildings(stop_flag)
                        stats['upgrades'] += upgraded
                        print(f"      Upgraded {upgraded} building(s)")

                    if stop_flag.should_stop():
                        break

                    # ===== 5. TRAIN TROOPS =====
                    if self.autopilot_settings['train_troops'] and training_configs:
                        print(f"\n{Colors.BOLD}[5/6] ⚔️  Training Troops...{Colors.END}")
                        results = self.military.multi_village_training_cycle(training_configs)
                        trained = results['total_barracks'] + results['total_stable']
                        stats['troops_trained'] += trained
                        print(f"      Trained {trained} troops in {results['villages_trained']} village(s)")

                    if stop_flag.should_stop():
                        break

                    # ===== 6. SEND FARMS =====
                    current_time = time.time()
                    if self.autopilot_settings['send_farms'] and \
                       (current_time - last_farm_time) >= self.autopilot_settings['farm_interval']:
                        print(f"\n{Colors.BOLD}[6/6] 🌾 Sending Farm Raids...{Colors.END}")
                        farm_results = self.farming.send_all_raids()
                        stats['raids_sent'] += farm_results['sent']
                        last_farm_time = current_time
                        print(f"      Sent {farm_results['sent']} raids")
                    else:
                        next_farm = int(self.autopilot_settings['farm_interval'] - (current_time - last_farm_time))
                        print(f"\n{Colors.BOLD}[6/6] 🌾 Farm Raids...{Colors.END}")
                        print(f"      Next raid wave in {next_farm}s")

                    # ===== AI ANALYSIS (periodically) =====
                    if self.autopilot_settings['ai_decisions'] and self._has_ai() and cycle % 10 == 0:
                        print(f"\n{Colors.BOLD}[AI] 🧠 Running AI Analysis...{Colors.END}")
                        self._autopilot_ai_decision(stats)
                        stats['ai_decisions'] += 1

                    # ===== CYCLE SUMMARY =====
                    print(f"\n{Colors.GREEN}✓ Cycle {cycle} complete{Colors.END}")
                    print(f"  Session stats: {stats['upgrades']} upgrades, {stats['troops_trained']} troops, {stats['raids_sent']} raids")
                    if stats['reconnections'] > 0:
                        print(f"  Reconnections: {stats['reconnections']}")

                    # Reset error counter on successful cycle
                    consecutive_errors = 0

                except Exception as e:
                    if is_connection_error(e):
                        consecutive_errors += 1
                        stats['reconnections'] += 1
                        print(f"\n{Colors.RED}⚠️  Connection error in cycle {cycle}: {str(e)[:80]}{Colors.END}")
                        self.logger.warning(f"Auto-pilot connection error: {e}")

                        # Wait for connection to be restored
                        if self.wait_for_connection(stop_flag):
                            print(f"{Colors.GREEN}Connection restored, resuming auto-pilot...{Colors.END}")
                            continue
                        else:
                            print(f"{Colors.RED}Could not restore connection, stopping auto-pilot{Colors.END}")
                            break
                    else:
                        # Non-connection error
                        consecutive_errors += 1
                        print(f"\n{Colors.RED}Error in cycle {cycle}: {e}{Colors.END}")
                        self.logger.error(f"Auto-pilot error: {e}")

                        if consecutive_errors >= max_consecutive_errors:
                            print(f"{Colors.RED}Too many consecutive errors, stopping auto-pilot{Colors.END}")
                            break
                        else:
                            print(f"{Colors.YELLOW}Continuing despite error ({consecutive_errors}/{max_consecutive_errors})...{Colors.END}")

                print(f"{Colors.RED}  [Press Q/S to stop]{Colors.END}")

                # Wait for next cycle
                wait_time = self.autopilot_settings['cycle_interval']
                print(f"\n  Next cycle in {wait_time}s...")

                for _ in range(wait_time):
                    if stop_flag.should_stop():
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()

        # Final summary
        print(f"\n{Colors.YELLOW}{'='*60}{Colors.END}")
        print(f"{Colors.YELLOW}   🤖 AI AUTO-PILOT DISENGAGED{Colors.END}")
        print(f"{Colors.YELLOW}{'='*60}{Colors.END}")
        print(f"\n{Colors.BOLD}Session Statistics:{Colors.END}")
        print(f"  Total cycles:      {cycle}")
        print(f"  Upgrades:          {stats['upgrades']}")
        print(f"  Troops trained:    {stats['troops_trained']}")
        print(f"  Raids sent:        {stats['raids_sent']}")
        print(f"  Attacks detected:  {stats['attacks_detected']}")
        print(f"  AI decisions:      {stats['ai_decisions']}")

        self.logger.info(f"Auto-pilot stopped: {cycle} cycles, {stats}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def _autopilot_upgrade_resources(self, stop_flag: StopFlag) -> int:
        """Upgrade resource fields for auto-pilot"""
        upgraded = 0
        target_level = 20

        for field_id in range(1, 19):
            if stop_flag.should_stop():
                break

            self.buildings.navigate_to_building(field_id)

            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            level = 0

            if h1:
                text = h1.text
                if 'Level' in text:
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        level = int(match.group(1))

            if level >= target_level:
                continue

            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
            if upgrade_btn:
                btn_class = upgrade_btn.get_attribute('class') or ''
                if 'disabled' not in btn_class:
                    upgrade_btn.click()
                    upgraded += 1
                    # Only upgrade one per cycle to balance resources
                    if self.autopilot_settings['priority'] != 'economy':
                        break

        return upgraded

    def _autopilot_upgrade_buildings(self, stop_flag: StopFlag) -> int:
        """Upgrade village buildings for auto-pilot"""
        upgraded = 0
        target_level = 20

        for building_id in range(19, 41):
            if stop_flag.should_stop():
                break

            self.buildings.navigate_to_building(building_id)

            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            level = 0
            name = "Empty"

            if h1:
                text = h1.text
                if 'Level' in text:
                    name = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        level = int(match.group(1))

            if name in ['Empty', 'Unknown'] or 'Construct' in str(name):
                continue

            if level >= target_level:
                continue

            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
            if upgrade_btn:
                btn_class = upgrade_btn.get_attribute('class') or ''
                if 'disabled' not in btn_class:
                    upgrade_btn.click()
                    upgraded += 1
                    # Only upgrade one per cycle
                    break

        return upgraded

    def _autopilot_ai_decision(self, stats: Dict):
        """Let AI analyze and potentially adjust strategy"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.anthropic_api_key)

            # Get current state
            game_state = f"""
Current auto-pilot stats:
- Upgrades performed: {stats['upgrades']}
- Troops trained: {stats['troops_trained']}
- Raids sent: {stats['raids_sent']}
- Attacks detected: {stats['attacks_detected']}

Resources: {self.resources.format_resources()}
Free crop: {self.resources.free_crop}
Priority mode: {self.autopilot_settings['priority']}
"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": f"Travian auto-pilot status check. {game_state}\n\nGive a brief (1-2 sentence) status assessment and any alerts. Be concise."
                }]
            )

            print(f"      {Colors.GREEN}AI: {response.content[0].text}{Colors.END}")

        except Exception as e:
            print(f"      AI analysis skipped: {e}")

    # ==================== NAVIGATION ====================

    def navigation_menu(self):
        """Quick navigation menu"""
        while True:
            clear_screen()
            print_header("NAVIGATION")

            print_menu("Go to", [
                "Resources (dorf1)",
                "Village center (dorf2)",
                "Map",
                "Statistics",
                "Reports",
                "Messages",
                "Hero",
                "Custom URL",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.session.navigate_to_village_overview()
            elif choice == "2":
                self.session.navigate_to_village_center()
            elif choice == "3":
                self.browser.navigate_to(f"{config.base_url}/karte.php")
            elif choice == "4":
                self.browser.navigate_to(f"{config.base_url}/statistiken.php")
            elif choice == "5":
                self.browser.navigate_to(f"{config.base_url}/berichte.php")
            elif choice == "6":
                self.browser.navigate_to(f"{config.base_url}/nachrichten.php")
            elif choice == "7":
                self.browser.navigate_to(f"{config.base_url}/hero_inventory.php")
            elif choice == "8":
                url = get_input("Enter URL path (e.g., build.php?id=1): ")
                self.browser.navigate_to(f"{config.base_url}/{url}")

            print(f"{Colors.GREEN}✓ Navigated{Colors.END}")
            time.sleep(1)

    # ==================== MULTI-TAB ====================

    def multitab_menu(self):
        """Multi-tab management menu"""
        while True:
            clear_screen()
            print_header("MULTI-TAB MANAGER")

            # Show current tabs
            tabs = self.browser.list_tabs()
            current = self.browser.get_current_tab()
            print(f"{Colors.BOLD}Open Tabs:{Colors.END}")
            for tab in tabs:
                marker = f"{Colors.GREEN}◀{Colors.END}" if tab == current else " "
                print(f"  {marker} {tab}")
            print()

            print_menu("Tab Options", [
                "Open new tab",
                "Switch to tab",
                "Close tab",
                "Run task in tab",
                "Parallel upgrades (all tabs)",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.open_new_tab()
            elif choice == "2":
                self.switch_to_tab()
            elif choice == "3":
                self.close_tab()
            elif choice == "4":
                self.run_task_in_tab()
            elif choice == "5":
                self.parallel_upgrades()

    def open_new_tab(self):
        """Open a new browser tab"""
        name = get_input("Tab name (e.g., 'village2', 'farm'): ")
        if not name:
            return

        print(f"\n{Colors.YELLOW}Opening new tab '{name}'...{Colors.END}")
        self.browser.new_tab(name, config.base_url)

        print(f"\n{Colors.YELLOW}Note: You may need to login in this tab too.{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def switch_to_tab(self):
        """Switch to a different tab"""
        tabs = self.browser.list_tabs()
        print(f"\nAvailable tabs: {', '.join(tabs)}")

        name = get_input("Switch to tab: ")
        if name in tabs:
            self.browser.switch_tab(name)
            print(f"{Colors.GREEN}✓ Switched to '{name}'{Colors.END}")
        else:
            print(f"{Colors.RED}Tab not found{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def close_tab(self):
        """Close a tab"""
        tabs = self.browser.list_tabs()
        print(f"\nAvailable tabs: {', '.join(tabs)}")

        name = get_input("Close tab: ")
        if name == 'main':
            print(f"{Colors.RED}Cannot close main tab{Colors.END}")
        elif name in tabs:
            self.browser.close_tab(name)
        else:
            print(f"{Colors.RED}Tab not found{Colors.END}")

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def run_task_in_tab(self):
        """Run a specific task in a tab"""
        tabs = self.browser.list_tabs()
        print(f"\nAvailable tabs: {', '.join(tabs)}")

        tab_name = get_input("Select tab: ")
        if tab_name not in tabs:
            print(f"{Colors.RED}Tab not found{Colors.END}")
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
            return

        print(f"\nTasks:")
        print("  1. Auto-upgrade resources")
        print("  2. Check status")
        print("  3. Scan buildings")

        task = get_input("Select task: ")

        # Switch to tab and run task
        self.browser.switch_tab(tab_name)

        if task == "1":
            print(f"\n{Colors.YELLOW}Running auto-upgrade in '{tab_name}'...{Colors.END}")
            self.buildings.auto_upgrade_resources(self.session)
        elif task == "2":
            self.session.navigate_to_village_overview()
            self.resources.update_resources()
            print(f"\n{Colors.GREEN}Resources in '{tab_name}':{Colors.END}")
            print(self.resources.format_resources())
        elif task == "3":
            self.buildings.scan_all_fields()

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def parallel_upgrades(self):
        """Run upgrades across all tabs in rotation"""
        clear_screen()
        print_header("PARALLEL UPGRADES")

        tabs = self.browser.list_tabs()
        print(f"Will cycle through {len(tabs)} tabs: {', '.join(tabs)}")
        print(f"\n{Colors.YELLOW}This will upgrade resources in each tab in rotation.{Colors.END}")
        print(f"{Colors.GREEN}Press 'Q' or 'S' to stop (or Ctrl+C){Colors.END}\n")

        confirm = get_input("Start parallel upgrades? (y/n): ")
        if confirm.lower() != 'y':
            return

        # Start key listener thread
        stop_flag = StopFlag()
        listener_thread = Thread(target=key_listener, args=(stop_flag,), daemon=True)
        listener_thread.start()

        total_upgrades = 0
        cycle = 0

        print(f"\n{Colors.RED}>>> Press 'Q' or 'S' to stop <<<{Colors.END}")

        try:
            while not stop_flag.should_stop():
                cycle += 1
                print(f"\n{Colors.CYAN}=== Cycle {cycle} ==={Colors.END}")

                for tab_name in tabs:
                    if stop_flag.should_stop():
                        break

                    print(f"\n{Colors.YELLOW}[{tab_name}]{Colors.END}")

                    # Switch to tab
                    if not self.browser.switch_tab(tab_name):
                        continue

                    # Try to upgrade one resource
                    result = self.buildings.auto_upgrade_resources(self.session)
                    if result:
                        total_upgrades += 1
                        print(f"  {Colors.GREEN}✓ Upgraded{Colors.END}")
                    else:
                        print(f"  No upgrades available")

                print(f"\nTotal upgrades this session: {total_upgrades}")
                print(f"{Colors.RED}[Press Q/S to stop]{Colors.END}")

                if not stop_flag.should_stop():
                    time.sleep(1)

        except KeyboardInterrupt:
            stop_flag.stop()

        print(f"\n\n{Colors.YELLOW}Stopped. Total upgrades: {total_upgrades}{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== TASK QUEUE ====================

    def show_background_tasks(self):
        """Show and manage task queue"""
        while True:
            clear_screen()
            print_header("TASK QUEUE")

            # Show executor status
            if self.task_executor.running:
                print(f"{Colors.GREEN}Task executor: RUNNING{Colors.END}\n")
            else:
                print(f"{Colors.YELLOW}Task executor: STOPPED{Colors.END}\n")

            # Show tasks
            tasks = self.task_executor.queue.get_all_tasks()
            if tasks:
                print(f"{'ID':<4} {'Name':<25} {'Status':<10} {'Runs':<6} {'Last Run':<10}")
                print("-" * 60)
                for task in tasks:
                    status_color = Colors.GREEN if task.status == TaskStatus.RUNNING else \
                                   Colors.YELLOW if task.status == TaskStatus.PENDING else \
                                   Colors.RED
                    print(f"{task.id:<4} {task.name:<25} {status_color}{task.status.value:<10}{Colors.END} {task.runs:<6} {task.last_run:<10}")
            else:
                print(f"{Colors.YELLOW}No tasks in queue{Colors.END}")

            print()
            print_menu("Options", [
                "Start task executor",
                "Stop task executor",
                "Add training task (single village)",
                "Add multi-village training task",
                "Add resource upgrade task",
                "Add village building upgrade task",
                "Add upgrade ALL task (resources + buildings)",
                "Add auto-farming task",
                "─────── ALL VILLAGES TASKS ───────",
                "🌍 Add ALL VILLAGES resource upgrade task",
                "🌍 Add ALL VILLAGES building upgrade task",
                "🌍 Add ALL VILLAGES smart build task",
                "─────────────────────────────────",
                "Remove a task",
                "Clear completed tasks",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                if self.task_executor.start():
                    print(f"{Colors.GREEN}✓ Task executor started{Colors.END}")
                else:
                    print(f"{Colors.YELLOW}Already running{Colors.END}")
                time.sleep(1)
            elif choice == "2":
                self.task_executor.stop()
                print(f"{Colors.GREEN}✓ Task executor stopped{Colors.END}")
                time.sleep(1)
            elif choice == "3":
                self.add_training_task_to_queue()
            elif choice == "4":
                self.add_multi_village_train_task_to_queue()
            elif choice == "5":
                self.add_upgrade_task_to_queue()
            elif choice == "6":
                self.add_village_upgrade_task_to_queue()
            elif choice == "7":
                self.add_all_upgrade_task_to_queue()
            elif choice == "8":
                self.add_farming_task_to_queue()
            elif choice == "9":
                pass  # Separator
            elif choice == "10":
                self.add_all_villages_upgrade_task_to_queue()
            elif choice == "11":
                self.add_all_villages_building_task_to_queue()
            elif choice == "12":
                self.add_all_villages_smart_build_task_to_queue()
            elif choice == "13":
                pass  # Separator
            elif choice == "14":
                task_id = get_input("Task ID to remove: ")
                try:
                    tid = int(task_id)
                    if self.task_executor.queue.remove_task(tid):
                        print(f"{Colors.GREEN}✓ Task removed{Colors.END}")
                    else:
                        print(f"{Colors.RED}Task not found{Colors.END}")
                except ValueError:
                    print(f"{Colors.RED}Invalid ID{Colors.END}")
                time.sleep(1)
            elif choice == "15":
                self.task_executor.queue.clear_completed()
                print(f"{Colors.GREEN}✓ Cleared completed tasks{Colors.END}")
                time.sleep(1)

    def add_training_task_to_queue(self):
        """Add a training task to the queue"""
        print("\nSelect building:")
        print("  1. Barracks")
        print("  2. Stable")
        building_choice = get_input("Building: ")
        building = 'barracks' if building_choice == '1' else 'stable'

        # Navigate and get troops
        if building == 'barracks':
            self.military.navigate_to_barracks()
        else:
            self.military.navigate_to_stable()

        available = self.military.get_available_troops_to_train()
        if not available:
            print(f"{Colors.RED}No troops found{Colors.END}")
            return

        print("\nAvailable troops:")
        for i, troop in enumerate(available, 1):
            print(f"  {i}. {troop['name']}")

        troop_choice = get_input("Select troop: ")
        try:
            idx = int(troop_choice) - 1
            if 0 <= idx < len(available):
                selected = available[idx]
                interval = get_input("Interval in seconds (default 30): ")
                interval = int(interval) if interval else 30

                self.task_executor.add_train_task(
                    building=building,
                    troop_name=selected['name'],
                    troop_input=selected['input_name'],
                    interval=interval
                )
        except ValueError:
            print(f"{Colors.RED}Invalid input{Colors.END}")

    def add_upgrade_task_to_queue(self):
        """Add a resource upgrade task to the queue"""
        target = get_input("Target level (default 20): ")
        target = int(target) if target else 20

        interval = get_input("Interval in seconds (default 30): ")
        interval = int(interval) if interval else 30

        self.task_executor.add_upgrade_task(target_level=target, interval=interval)
        print(f"{Colors.GREEN}✓ Resource upgrade task added{Colors.END}")
        time.sleep(1)

    def add_village_upgrade_task_to_queue(self):
        """Add a village building upgrade task to the queue"""
        target = get_input("Target level (default 20): ")
        target = int(target) if target else 20

        interval = get_input("Interval in seconds (default 30): ")
        interval = int(interval) if interval else 30

        self.task_executor.add_village_upgrade_task(target_level=target, interval=interval)
        print(f"{Colors.GREEN}✓ Village building upgrade task added{Colors.END}")
        time.sleep(1)

    def add_all_upgrade_task_to_queue(self):
        """Add both resource and village building upgrade tasks to the queue"""
        target = get_input("Target level (default 20): ")
        target = int(target) if target else 20

        interval = get_input("Interval in seconds (default 30): ")
        interval = int(interval) if interval else 30

        self.task_executor.add_upgrade_task(target_level=target, interval=interval)
        self.task_executor.add_village_upgrade_task(target_level=target, interval=interval)
        print(f"{Colors.GREEN}✓ Both resource and village upgrade tasks added{Colors.END}")
        time.sleep(1)

    def add_farming_task_to_queue(self):
        """Add an auto-farming task to the queue"""
        enabled = len(self.farming.get_enabled_farms())
        if enabled == 0:
            print(f"{Colors.RED}No enabled farms! Add farms first in Farm List Manager.{Colors.END}")
            time.sleep(2)
            return

        print(f"\n{Colors.GREEN}Will raid {enabled} enabled farm(s){Colors.END}")

        interval = get_input(f"Raid interval in seconds (default {self.farming.raid_interval}): ")
        try:
            interval = int(interval) if interval else self.farming.raid_interval
        except ValueError:
            interval = self.farming.raid_interval

        self.task_executor.add_farming_task(interval=interval)
        print(f"{Colors.GREEN}✓ Auto-farming task added (every {interval}s){Colors.END}")
        time.sleep(1)

    def add_multi_village_train_task_to_queue(self):
        """Add a multi-village training task to the queue"""
        configs = self.military.load_village_training_configs()

        if not configs:
            print(f"{Colors.RED}No village training configs! Set up first in Military menu.{Colors.END}")
            time.sleep(2)
            return

        enabled = len([c for c in configs.values() if c.enabled])
        print(f"\n{Colors.GREEN}Will train in {enabled} configured village(s){Colors.END}")

        interval = get_input("Training interval in seconds (default 60): ")
        try:
            interval = int(interval) if interval else 60
        except ValueError:
            interval = 60

        self.task_executor.add_multi_village_train_task(interval=interval)
        print(f"{Colors.GREEN}✓ Multi-village training task added (every {interval}s){Colors.END}")
        time.sleep(1)

    def add_all_villages_upgrade_task_to_queue(self):
        """Add a task to upgrade resources in ALL villages"""
        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            time.sleep(2)
            return

        print(f"\n{Colors.GREEN}Will upgrade resources in {len(villages)} village(s){Colors.END}")

        target = get_input("Target level (default 20): ")
        target = int(target) if target else 20

        interval = get_input("Interval in seconds (default 60): ")
        try:
            interval = int(interval) if interval else 60
        except ValueError:
            interval = 60

        self.task_executor.add_all_villages_upgrade_task(target_level=target, interval=interval)
        print(f"{Colors.GREEN}✓ ALL VILLAGES resource upgrade task added (every {interval}s){Colors.END}")
        time.sleep(1)

    def add_all_villages_building_task_to_queue(self):
        """Add a task to upgrade buildings in ALL villages"""
        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            time.sleep(2)
            return

        print(f"\n{Colors.GREEN}Will upgrade buildings in {len(villages)} village(s){Colors.END}")

        target = get_input("Target level (default 20): ")
        target = int(target) if target else 20

        interval = get_input("Interval in seconds (default 60): ")
        try:
            interval = int(interval) if interval else 60
        except ValueError:
            interval = 60

        self.task_executor.add_all_villages_building_task(target_level=target, interval=interval)
        print(f"{Colors.GREEN}✓ ALL VILLAGES building upgrade task added (every {interval}s){Colors.END}")
        time.sleep(1)

    def add_all_villages_smart_build_task_to_queue(self):
        """Add a smart build task for ALL villages"""
        villages = self.village_cycler.get_all_villages()
        if not villages:
            print(f"{Colors.RED}No villages found!{Colors.END}")
            time.sleep(2)
            return

        print(f"\n{Colors.GREEN}Will run smart build in {len(villages)} village(s){Colors.END}")

        interval = get_input("Interval in seconds (default 120): ")
        try:
            interval = int(interval) if interval else 120
        except ValueError:
            interval = 120

        self.task_executor.add_all_villages_smart_build_task(interval=interval)
        print(f"{Colors.GREEN}✓ ALL VILLAGES smart build task added (every {interval}s){Colors.END}")
        time.sleep(1)

    # ==================== VILLAGE MAP ====================

    def village_map_menu(self):
        """Village mapping and caching menu"""
        while True:
            clear_screen()
            print_header("VILLAGE MAP")

            # Show cached villages
            cached = list(self.village_map.villages.keys())
            if cached:
                print(f"{Colors.GREEN}Cached villages: {', '.join(cached)}{Colors.END}\n")
            else:
                print(f"{Colors.YELLOW}No villages cached yet{Colors.END}\n")

            print_menu("Map Options", [
                "🔍 Scan current village",
                "📋 View village summary",
                "🔄 Re-scan (force refresh)",
                "🗑️  Clear cache",
                "🏠 Find building by name",
                "🔀 Test village switcher",
            ])

            choice = get_input()

            if choice == "0":
                break
            elif choice == "1":
                self.scan_village()
            elif choice == "2":
                self.view_village_summary()
            elif choice == "3":
                self.scan_village(force=True)
            elif choice == "4":
                self.clear_village_cache()
            elif choice == "5":
                self.find_building()
            elif choice == "6":
                self.test_village_switcher()

    def scan_village(self, force: bool = False):
        """Scan current village"""
        clear_screen()
        print_header("SCANNING VILLAGE")
        self.village_map.scan_village(force=force)
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def view_village_summary(self):
        """View village summary"""
        clear_screen()
        print_header("VILLAGE SUMMARY")
        self.village_map.print_summary()
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def clear_village_cache(self):
        """Clear village cache"""
        confirm = get_input("Clear all cached village data? (y/n): ")
        if confirm.lower() == 'y':
            self.village_map.clear_cache()
            print(f"{Colors.GREEN}✓ Cache cleared{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def find_building(self):
        """Find building slot by name"""
        name = get_input("Building name to find: ")
        if name:
            slot = self.village_map.get_building_slot(name)
            if slot:
                print(f"\n{Colors.GREEN}Found '{name}' at slot #{slot}{Colors.END}")
            else:
                print(f"\n{Colors.RED}Building '{name}' not found{Colors.END}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    def test_village_switcher(self):
        """Test village switching functionality"""
        clear_screen()
        print_header("VILLAGE SWITCHER TEST")
        print(f"{Colors.YELLOW}This test will:{Colors.END}")
        print("  1. Find all your villages")
        print("  2. Try switching to each one")
        print("  3. Verify the switch worked")
        print("  4. Return to original village")
        print()

        confirm = get_input("Run village switcher test? (y/n): ")
        if confirm.lower() != 'y':
            return

        print()
        from test_village_switcher import VillageSwitcherTest
        tester = VillageSwitcherTest(self.browser)
        results = tester.run_test()

        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")

    # ==================== MAIN MENU ====================

    def main_menu(self):
        """Main menu loop"""
        while True:
            clear_screen()

            # Task queue status
            task_count = len(self.task_executor.queue.get_active_tasks()) if self.task_executor else 0
            executor_status = "RUNNING" if (self.task_executor and self.task_executor.running) else "STOPPED"
            status_color = Colors.GREEN if executor_status == "RUNNING" else Colors.YELLOW
            task_status = f"{status_color}{executor_status}{Colors.END} ({task_count} tasks)"

            print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════╗
║{Colors.END}{Colors.BOLD}{Colors.YELLOW}           TRAVIAN AI ASSISTANT - INTERACTIVE             {Colors.END}{Colors.CYAN}║
╠══════════════════════════════════════════════════════════╣
║{Colors.END}  Server: {config.server:<47}{Colors.CYAN}║
║{Colors.END}  User: {config.username:<49}{Colors.CYAN}║
║{Colors.END}  Task Queue: {task_status:<44}{Colors.CYAN}║
╚══════════════════════════════════════════════════════════╝{Colors.END}
""")

            print_menu("MAIN MENU", [
                "📊 View Status",
                "🏗️  Buildings",
                "⚔️  Military",
                "🌾 Farm List Manager",
                "🤖 AI AUTO-PILOT (Full Automation)",
                "🔄 Simple Auto Mode",
                "🧭 Navigation",
                "📑 Multi-Tab Manager",
                "🗺️  Village Map (scan & cache)",
                f"⏳ Task Queue ({task_count} active)",
                "⚙️  Settings",
                "📨 Reports Manager",
                "📸 Take Screenshot",
            ])

            choice = get_input("Select option: ")

            if choice == "0":
                confirm = get_input("Exit bot? (y/n): ")
                if confirm.lower() == 'y':
                    break
            elif choice == "1":
                self.show_status()
            elif choice == "2":
                self.buildings_menu()
            elif choice == "3":
                self.military_menu()
            elif choice == "4":
                self.farming_menu()
            elif choice == "5":
                self.autopilot_menu()
            elif choice == "6":
                self.auto_mode_menu()
            elif choice == "7":
                self.navigation_menu()
            elif choice == "8":
                self.multitab_menu()
            elif choice == "9":
                self.village_map_menu()
            elif choice == "10":
                self.show_background_tasks()
            elif choice == "11":
                self.settings_menu()
            elif choice == "12":
                self.reports_menu()
            elif choice == "13":
                self.browser.screenshot(f'manual_{datetime.now().strftime("%H%M%S")}.png')
                print(f"{Colors.GREEN}✓ Screenshot saved{Colors.END}")
                time.sleep(1)

    def run(self):
        """Main entry point"""
        clear_screen()
        print(f"""
{Colors.CYAN}
  ████████╗██████╗  █████╗ ██╗   ██╗██╗ █████╗ ███╗   ██╗
  ╚══██╔══╝██╔══██╗██╔══██╗██║   ██║██║██╔══██╗████╗  ██║
     ██║   ██████╔╝███████║██║   ██║██║███████║██╔██╗ ██║
     ██║   ██╔══██╗██╔══██║╚██╗ ██╔╝██║██╔══██║██║╚██╗██║
     ██║   ██║  ██║██║  ██║ ╚████╔╝ ██║██║  ██║██║ ╚████║
     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
{Colors.END}
{Colors.YELLOW}              AI Assistant - Interactive Mode{Colors.END}
{Colors.CYAN}{'='*60}{Colors.END}
""")

        self.logger.info("=" * 50)
        self.logger.info("Interactive Bot starting...")
        self.logger.info(f"Server: {config.server}")
        self.logger.info(f"Username: {config.username}")

        # Load saved settings
        try:
            with open('bot_settings.json', 'r') as f:
                self.settings = json.load(f)
                print(f"{Colors.GREEN}✓ Loaded saved settings{Colors.END}")
                self.logger.info("Loaded saved settings")
        except:
            pass

        # Initialize
        if not self.initialize():
            return 1

        # Login
        if not self.login():
            print(f"{Colors.RED}Login failed{Colors.END}")
            self.shutdown()
            return 1

        # Run main menu
        try:
            self.main_menu()
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.END}")
            self.logger.error(f"Error in main menu: {e}")
            self.action_log.log_error("main_menu", str(e))
        finally:
            self.shutdown()

        return 0


def main():
    bot = InteractiveBot()
    sys.exit(bot.run())


if __name__ == "__main__":
    main()
