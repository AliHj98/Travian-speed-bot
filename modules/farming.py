"""
Farming Module - Farm list management and automated raiding
"""

import json
import math
import os
import time
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from core.browser import BrowserManager
from config import config

# Troop speeds in fields/hour by tribe and troop input name
TROOP_SPEEDS: Dict[str, Dict[str, int]] = {
    'romans': {
        't1': 6, 't2': 5, 't3': 7, 't4': 16, 't5': 14,
        't6': 10, 't7': 4, 't8': 3, 't9': 4, 't10': 5, 't11': 35,
    },
    'gauls': {
        't1': 7, 't2': 6, 't3': 17, 't4': 19, 't5': 16,
        't6': 13, 't7': 4, 't8': 3, 't9': 5, 't10': 5, 't11': 35,
    },
    'teutons': {
        't1': 7, 't2': 7, 't3': 6, 't4': 9, 't5': 10,
        't6': 9, 't7': 4, 't8': 3, 't9': 4, 't10': 5, 't11': 35,
    },
}


@dataclass
class FarmTarget:
    """A single farm target"""
    id: int
    name: str
    x: int
    y: int
    troops: Dict[str, int]  # troop_input_name -> amount
    last_raid: str = ""
    raids_sent: int = 0
    enabled: bool = True
    notes: str = ""
    travel_time: int = 0  # round-trip travel time in seconds (0 = unknown)
    next_raid_at: float = 0  # timestamp when next raid should fire


class FarmListManager:
    """Manages farm lists and automated farming"""

    FARM_FILE = 'farm_list.json'

    # Common troop input names by tribe
    TROOP_INPUTS = {
        'romans': {
            'Legionnaire': 't1',
            'Praetorian': 't2',
            'Imperian': 't3',
            'Equites Legati': 't4',
            'Equites Imperatoris': 't5',
            'Equites Caesaris': 't6',
            'Battering Ram': 't7',
            'Fire Catapult': 't8',
            'Senator': 't9',
            'Settler': 't10',
            'Hero': 't11',
        },
        'gauls': {
            'Phalanx': 't1',
            'Swordsman': 't2',
            'Pathfinder': 't3',
            'Theutates Thunder': 't4',
            'Druidrider': 't5',
            'Haeduan': 't6',
            'Battering Ram': 't7',
            'Trebuchet': 't8',
            'Chieftain': 't9',
            'Settler': 't10',
            'Hero': 't11',
        },
        'teutons': {
            'Clubswinger': 't1',
            'Spearfighter': 't2',
            'Axefighter': 't3',
            'Scout': 't4',
            'Paladin': 't5',
            'Teutonic Knight': 't6',
            'Battering Ram': 't7',
            'Catapult': 't8',
            'Chief': 't9',
            'Settler': 't10',
            'Hero': 't11',
        },
    }

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.farms: Dict[int, FarmTarget] = {}
        self.farm_counter = 0
        self.default_troops: Dict[str, int] = {}  # Default troops for new farms
        self.raid_interval = 300  # Seconds between raid cycles
        self.tribe: str = 'romans'  # Default tribe, used for speed lookups
        self.server_speed: int = 1  # Server speed multiplier
        self.home_x: int = 0  # Home village coordinates
        self.home_y: int = 0
        self.load_farms()

    def load_farms(self):
        """Load farm list from file"""
        try:
            if os.path.exists(self.FARM_FILE):
                with open(self.FARM_FILE, 'r') as f:
                    data = json.load(f)
                    self.farm_counter = data.get('counter', 0)
                    self.default_troops = data.get('default_troops', {})
                    self.raid_interval = data.get('raid_interval', 300)
                    self.tribe = data.get('tribe', 'romans')
                    self.server_speed = data.get('server_speed', 1)
                    self.home_x = data.get('home_x', 0)
                    self.home_y = data.get('home_y', 0)

                    for farm_data in data.get('farms', []):
                        farm = FarmTarget(**farm_data)
                        self.farms[farm.id] = farm

                print(f"✓ Loaded {len(self.farms)} farm(s)")
        except Exception as e:
            print(f"Could not load farms: {e}")
            self.farms = {}

    def save_farms(self):
        """Save farm list to file"""
        try:
            data = {
                'counter': self.farm_counter,
                'default_troops': self.default_troops,
                'raid_interval': self.raid_interval,
                'tribe': self.tribe,
                'server_speed': self.server_speed,
                'home_x': self.home_x,
                'home_y': self.home_y,
                'farms': [asdict(farm) for farm in self.farms.values()]
            }
            with open(self.FARM_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Could not save farms: {e}")

    def add_farm(self, name: str, x: int, y: int, troops: Dict[str, int] = None, notes: str = "") -> int:
        """Add a new farm target"""
        self.farm_counter += 1
        farm = FarmTarget(
            id=self.farm_counter,
            name=name,
            x=x,
            y=y,
            troops=troops or self.default_troops.copy(),
            notes=notes
        )
        self.farms[farm.id] = farm
        self.save_farms()
        print(f"✓ Farm #{farm.id} added: {name} ({x}|{y})")
        return farm.id

    def remove_farm(self, farm_id: int) -> bool:
        """Remove a farm from the list"""
        if farm_id in self.farms:
            del self.farms[farm_id]
            self.save_farms()
            return True
        return False

    def toggle_farm(self, farm_id: int) -> bool:
        """Enable/disable a farm"""
        if farm_id in self.farms:
            self.farms[farm_id].enabled = not self.farms[farm_id].enabled
            self.save_farms()
            return True
        return False

    def update_farm_troops(self, farm_id: int, troops: Dict[str, int]):
        """Update troops for a specific farm"""
        if farm_id in self.farms:
            self.farms[farm_id].troops = troops
            self.save_farms()

    def set_default_troops(self, troops: Dict[str, int]):
        """Set default troops for new farms"""
        self.default_troops = troops
        self.save_farms()
        print(f"✓ Default troops set: {troops}")

    def get_all_farms(self) -> List[FarmTarget]:
        """Get all farms"""
        return list(self.farms.values())

    def get_enabled_farms(self) -> List[FarmTarget]:
        """Get only enabled farms"""
        return [f for f in self.farms.values() if f.enabled]

    def estimate_travel_time(self, farm: FarmTarget) -> int:
        """Estimate round-trip travel time in seconds based on distance and slowest troop speed"""
        distance = math.sqrt((farm.x - self.home_x) ** 2 + (farm.y - self.home_y) ** 2)
        if distance == 0:
            return 0

        tribe_speeds = TROOP_SPEEDS.get(self.tribe, TROOP_SPEEDS['romans'])

        # Find the slowest troop in the raid group
        slowest_speed = None
        for troop_key, amount in farm.troops.items():
            if amount > 0 and troop_key in tribe_speeds:
                speed = tribe_speeds[troop_key]
                if slowest_speed is None or speed < slowest_speed:
                    slowest_speed = speed

        if slowest_speed is None:
            return 0

        # Apply server speed multiplier
        effective_speed = slowest_speed * self.server_speed
        # One-way time in hours, then round trip, convert to seconds
        one_way_hours = distance / effective_speed
        round_trip_seconds = int(one_way_hours * 2 * 3600)
        return round_trip_seconds

    def parse_travel_time_from_page(self) -> Optional[int]:
        """Parse actual travel duration from the confirmation/movements page after sending a raid.
        Returns one-way travel time in seconds, or None if not found."""
        try:
            # Look for travel duration on the page (e.g. "0:12:34" or "in 12:34")
            duration_selectors = [
                'div.in',  # common Travian duration container
                '.dur', '.duration',
                'td.dur', 'span.timer',
                '.at',  # arrival time container
            ]
            for sel in duration_selectors:
                elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if elem:
                    text = elem.text.strip()
                    match = re.search(r'(\d+):(\d{2}):(\d{2})', text)
                    if match:
                        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        return h * 3600 + m * 60 + s

            # Fallback: search entire page source for duration pattern near "Duration"
            page = self.browser.driver.page_source or ""
            match = re.search(r'[Dd]uration.*?(\d+):(\d{2}):(\d{2})', page)
            if match:
                h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return h * 3600 + m * 60 + s
        except Exception as e:
            print(f"  Could not parse travel time: {e}")
        return None

    def navigate_to_rally_point(self) -> bool:
        """Navigate to the rally point"""
        # Rally point is typically at slot 39
        rally_point_slots = [39, 38, 37]  # Try common slots

        for slot in rally_point_slots:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")

            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1 and 'Rally Point' in h1.text:
                return True

        # Try to find by scanning
        for slot in range(19, 41):
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1 and 'Rally Point' in h1.text:
                return True

        print("  ✗ Rally Point not found")
        return False

    def debug_rally_point(self):
        """Debug the rally point page to find correct selectors"""
        print("\n=== DEBUG: Rally Point Page ===")

        # Navigate to rally point send troops tab
        self.browser.navigate_to(f"{config.base_url}/build.php?id=39&tt=2")
        time.sleep(0.5)

        # Find all inputs
        all_inputs = self.browser.driver.find_elements(By.CSS_SELECTOR, 'input')
        print(f"\nAll inputs ({len(all_inputs)}):")
        for inp in all_inputs:
            try:
                name = inp.get_attribute('name') or ''
                inp_id = inp.get_attribute('id') or ''
                inp_type = inp.get_attribute('type') or ''
                placeholder = inp.get_attribute('placeholder') or ''
                visible = inp.is_displayed()
                print(f"  name='{name}' id='{inp_id}' type='{inp_type}' placeholder='{placeholder}' visible={visible}")
            except:
                pass

        # Find coordinate-related elements
        print("\nLooking for coordinate inputs...")
        coord_selectors = [
            'input[name="x"]', 'input[name="y"]',
            'input[name="xCoordinate"]', 'input[name="yCoordinate"]',
            'input#xCoordInput', 'input#yCoordInput',
            'input.coordinateX', 'input.coordinateY',
            'input[placeholder*="X"]', 'input[placeholder*="Y"]',
            '.координаты input', '.coordinates input',
            'input[name*="coord"]', 'input[id*="coord"]',
        ]

        for sel in coord_selectors:
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if elem:
                print(f"  ✓ Found: {sel}")

        print("\n=== END DEBUG ===\n")

    def coords_to_map_id(self, x: int, y: int) -> int:
        """Convert x,y coordinates to Travian map ID (z parameter)"""
        # Travian map ID formula: (400 + x) * 801 + (400 + y) + 1
        # This converts coordinates like (-32, 45) to map ID
        return (400 + x) * 801 + (400 + y) + 1

    def _fill_coordinates(self, x: int, y: int) -> bool:
        """Try to fill coordinate inputs on the current page"""
        coord_filled = False

        # Try x coordinate
        x_selectors = [
            'input[name="x"]',
            'input[name="xCoordinate"]',
            'input#xCoordInput',
            'input.coordinateX',
        ]
        for sel in x_selectors:
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if elem:
                elem.clear()
                elem.send_keys(str(x))
                coord_filled = True
                break

        # Try y coordinate
        y_selectors = [
            'input[name="y"]',
            'input[name="yCoordinate"]',
            'input#yCoordInput',
            'input.coordinateY',
        ]
        for sel in y_selectors:
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if elem:
                elem.clear()
                elem.send_keys(str(y))
                coord_filled = True
                break

        return coord_filled

    def send_raid(self, farm: FarmTarget) -> bool:
        """Send a raid to a farm target"""
        try:
            # Navigate to the send troops page and fill coordinates
            attack_url = f"{config.base_url}/a2b.php"
            print(f"  Navigating to: {attack_url}")
            self.browser.navigate_to(attack_url)
            time.sleep(0.5)

            # Check if page loaded, fallback to rally point
            if 'a2b.php' not in (self.browser.current_url or '') and 'build.php' not in (self.browser.current_url or ''):
                print(f"  a2b.php redirect, trying rally point...")
                self.browser.navigate_to(f"{config.base_url}/build.php?id=39&tt=2")
                time.sleep(0.5)

            self._fill_coordinates(farm.x, farm.y)

            # Enter troops
            troops_entered = False
            for troop_input, amount in farm.troops.items():
                if amount > 0:
                    # Try different input name patterns
                    input_elem = None
                    for selector in [
                        f'input[name="{troop_input}"]',
                        f'input[name="troops[{troop_input}]"]',
                        f'input[name="troop[{troop_input}]"]',
                        f'input.troop{troop_input}',
                    ]:
                        input_elem = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                        if input_elem:
                            break

                    if input_elem:
                        input_elem.clear()
                        input_elem.send_keys(str(amount))
                        troops_entered = True

            if not troops_entered:
                print(f"  ✗ No troops entered for {farm.name}")
                return False

            # Select raid option (radio button)
            raid_options = [
                'input[value="4"]',  # Raid
                'input[name="c"][value="4"]',
                'input[name="eventType"][value="4"]',
                '#rallyPointAttack input[value="4"]',
            ]

            raid_selected = False
            for selector in raid_options:
                raid_btn = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                if raid_btn:
                    try:
                        raid_btn.click()
                        raid_selected = True
                        break
                    except:
                        continue

            # Click send/submit button
            submit_btns = [
                'button[type="submit"]',
                'button.green',
                'button.textButtonV1',
                'input[type="submit"]',
                '#btn_ok',
            ]

            for selector in submit_btns:
                btn = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                if btn:
                    btn.click()
                    time.sleep(0.5)
                    break

            # Check for errors (not enough troops, etc.)
            page_text = (self.browser.driver.page_source or "").lower()
            error_indicators = [
                'not enough', 'zu wenig', 'недостаточно',
                'no troops', 'keine truppen',
                'error', 'fehler',
            ]
            # Also check if we're still on the send form (no confirmation page appeared)
            has_error = any(ind in page_text for ind in error_indicators)
            # Check for the confirmation page - it should have troop movement details
            has_confirm = False
            confirm_btns = [
                'button[type="submit"]',
                'button.green',
                'button#btn_ok',
                'input[type="submit"][name="s1"]',
            ]

            for selector in confirm_btns:
                btn = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                if btn:
                    has_confirm = True
                    break

            if has_error or not has_confirm:
                print(f"  ✗ Not enough troops for {farm.name} (or page error)")
                # Navigate back to main page to recover
                try:
                    self.browser.navigate_to(config.base_url)
                    time.sleep(0.5)
                except:
                    pass
                # Schedule a retry in 60 seconds so the loop keeps going
                farm.next_raid_at = time.time() + 60
                self.save_farms()
                return False

            # Confirm the raid (second page)
            for selector in confirm_btns:
                btn = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                if btn:
                    btn.click()
                    break

            time.sleep(0.5)

            # Try to read actual travel time from the page
            one_way = self.parse_travel_time_from_page()
            if one_way:
                farm.travel_time = one_way * 2
                print(f"  Travel time (from page): {one_way}s one-way, {farm.travel_time}s round-trip")
            elif farm.travel_time == 0:
                # Fall back to estimated calculation
                estimated = self.estimate_travel_time(farm)
                if estimated > 0:
                    farm.travel_time = estimated
                    print(f"  Travel time (estimated): {farm.travel_time}s round-trip")

            # Schedule next raid
            if farm.travel_time > 0:
                farm.next_raid_at = time.time() + farm.travel_time
                print(f"  Next raid at: {datetime.fromtimestamp(farm.next_raid_at).strftime('%H:%M:%S')}")

            # Update farm stats
            farm.last_raid = datetime.now().strftime('%H:%M:%S')
            farm.raids_sent += 1
            self.save_farms()

            print(f"  ✓ Raid sent to {farm.name} ({farm.x}|{farm.y})")
            return True

        except Exception as e:
            print(f"  ✗ Failed to raid {farm.name}: {e}")
            # Navigate to main page to recover from broken/error pages
            try:
                self.browser.navigate_to(config.base_url)
                time.sleep(0.5)
            except:
                pass
            # Schedule retry so the loop keeps going
            farm.next_raid_at = time.time() + 60
            self.save_farms()
            return False

    def send_all_raids(self) -> Dict:
        """Send raids to all enabled farms"""
        results = {
            'sent': 0,
            'failed': 0,
            'skipped': 0,
        }

        enabled_farms = self.get_enabled_farms()

        if not enabled_farms:
            print("No enabled farms in the list")
            return results

        print(f"\n🎯 Sending raids to {len(enabled_farms)} farm(s)...")

        for farm in enabled_farms:
            if not farm.troops:
                print(f"  ⚠ Skipping {farm.name} - no troops configured")
                results['skipped'] += 1
                continue

            if self.send_raid(farm):
                results['sent'] += 1
            else:
                results['failed'] += 1

            time.sleep(0.5)  # Small delay between raids

        print(f"\n✓ Raids: {results['sent']} sent, {results['failed']} failed, {results['skipped']} skipped")
        return results

    def auto_raid_loop(self, stop_callback) -> Dict:
        """Continuously re-send raids based on each farm's travel time.
        stop_callback: callable that returns True when the loop should stop.
        Returns stats dict."""
        stats = {'total_sent': 0, 'total_failed': 0}
        enabled_farms = self.get_enabled_farms()

        if not enabled_farms:
            print("No enabled farms in the list")
            return stats

        # Initial wave: send raids to all farms that are due or have no schedule
        now = time.time()
        for farm in enabled_farms:
            if not farm.troops:
                continue
            if farm.next_raid_at <= now:
                print(f"\n  Raiding {farm.name} ({farm.x}|{farm.y})...")
                if self.send_raid(farm):
                    stats['total_sent'] += 1
                else:
                    stats['total_failed'] += 1
                time.sleep(0.5)

        # Main loop: check each farm individually
        while not stop_callback():
            now = time.time()
            # Find the next farm that's due
            for farm in self.get_enabled_farms():
                if not farm.troops or not farm.enabled:
                    continue
                if farm.next_raid_at > 0 and now >= farm.next_raid_at:
                    print(f"\n  Troops returned! Re-raiding {farm.name} ({farm.x}|{farm.y})...")
                    if self.send_raid(farm):
                        stats['total_sent'] += 1
                    else:
                        stats['total_failed'] += 1
                    time.sleep(0.5)

            # Print status of upcoming raids
            upcoming = []
            for farm in self.get_enabled_farms():
                if farm.next_raid_at > time.time() and farm.troops:
                    wait = int(farm.next_raid_at - time.time())
                    upcoming.append(f"    {farm.name}: {wait}s")
            if upcoming:
                print(f"\n  Waiting for troops to return:")
                for line in upcoming:
                    print(line)

            # Sleep in small increments to stay responsive to stop signal
            for _ in range(7):  # ~7 seconds between checks
                if stop_callback():
                    break
                time.sleep(1)

        return stats

    def get_available_troops(self) -> Dict[str, int]:
        """Get available troops from rally point"""
        troops = {}

        try:
            self.browser.navigate_to(f"{config.base_url}/build.php?id=39&tt=2")

            # Find all troop inputs and their max values
            inputs = self.browser.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"]')

            for inp in inputs:
                name = inp.get_attribute('name') or ''
                if name.startswith('t') or 'troop' in name.lower():
                    # Try to find the max available
                    try:
                        parent = inp.find_element(By.XPATH, './..')
                        text = parent.text
                        # Look for a number that indicates available troops
                        match = re.search(r'(\d+)', text)
                        if match:
                            troops[name] = int(match.group(1))
                    except:
                        pass
        except Exception as e:
            print(f"Error getting troops: {e}")

        return troops

    def scan_map_for_farms(self, center_x: int, center_y: int, radius: int = 5) -> List[Dict]:
        """Scan the map around coordinates for potential farms (oases, inactive players)"""
        potential_farms = []

        print(f"🔍 Scanning map around ({center_x}|{center_y}) radius {radius}...")

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                x = center_x + dx
                y = center_y + dy

                # Skip center
                if dx == 0 and dy == 0:
                    continue

                try:
                    self.browser.navigate_to(f"{config.base_url}/position_details.php?x={x}&y={y}")

                    # Check if it's an oasis or village
                    content = self.browser.find_element_fast(By.CSS_SELECTOR, '#tileDetails')
                    if content:
                        text = content.text.lower()

                        # Check for oasis
                        if 'oasis' in text:
                            potential_farms.append({
                                'x': x,
                                'y': y,
                                'type': 'oasis',
                                'name': f"Oasis ({x}|{y})"
                            })
                        # Check for inactive/abandoned villages
                        elif 'inactive' in text or 'abandoned' in text:
                            potential_farms.append({
                                'x': x,
                                'y': y,
                                'type': 'inactive',
                                'name': f"Inactive ({x}|{y})"
                            })

                except:
                    pass

        print(f"✓ Found {len(potential_farms)} potential farms")
        return potential_farms

    def print_farm_list(self):
        """Print the farm list"""
        farms = self.get_all_farms()

        if not farms:
            print("No farms in the list")
            return

        print(f"\n{'ID':<4} {'Status':<8} {'Name':<20} {'Coords':<12} {'Raids':<6} {'Last Raid':<10}")
        print("-" * 70)

        for farm in farms:
            status = "✓ ON" if farm.enabled else "✗ OFF"
            coords = f"({farm.x}|{farm.y})"
            print(f"{farm.id:<4} {status:<8} {farm.name:<20} {coords:<12} {farm.raids_sent:<6} {farm.last_raid:<10}")

        print(f"\nTotal: {len(farms)} farms | Enabled: {len(self.get_enabled_farms())}")

    def print_farm_details(self, farm_id: int):
        """Print details of a specific farm"""
        if farm_id not in self.farms:
            print("Farm not found")
            return

        farm = self.farms[farm_id]
        print(f"\n{'='*40}")
        print(f"Farm #{farm.id}: {farm.name}")
        print(f"{'='*40}")
        print(f"Coordinates: ({farm.x}|{farm.y})")
        print(f"Status: {'Enabled' if farm.enabled else 'Disabled'}")
        print(f"Raids sent: {farm.raids_sent}")
        print(f"Last raid: {farm.last_raid or 'Never'}")
        print(f"Notes: {farm.notes or 'None'}")
        print(f"\nTroops:")
        if farm.troops:
            for troop, amount in farm.troops.items():
                if amount > 0:
                    print(f"  {troop}: {amount}")
        else:
            print("  No troops configured")
