import re
import time
from typing import Dict, List, Optional
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from modules.resources import ResourceMonitor


class BuildingManager:
    """Manages village buildings - AUTO UPGRADE TO LEVEL 20"""

    BUILDING_PRIORITIES = {
        'Woodcutter': 100, 'Clay Pit': 100, 'Iron Mine': 100, 'Cropland': 120,
        'Warehouse': 80, 'Granary': 80, 'Main Building': 90,
        'Barracks': 70, 'Stable': 60, 'Workshop': 50, 'Academy': 85, 'Smithy': 65,
        'Rally Point': 75, 'Marketplace': 55, 'Embassy': 40, 'Palace': 95, 'Residence': 95,
    }

    def __init__(self, browser: BrowserManager, resource_monitor: ResourceMonitor):
        self.browser = browser
        self.resources = resource_monitor
        self.target_level = 20

    def navigate_to_building(self, building_id: int):
        """Navigate to a specific building"""
        from config import config
        self.browser.navigate_to(f"{config.base_url}/build.php?id={building_id}")

    def get_building_info(self, building_id: int) -> Optional[Dict]:
        """Get building info"""
        try:
            self.navigate_to_building(building_id)

            info = {'id': building_id, 'name': 'Unknown', 'level': 0, 'can_upgrade': False}

            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                text = h1.text
                if 'Level' in text:
                    info['name'] = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        info['level'] = int(match.group(1))
                else:
                    info['name'] = text.strip()

            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
            if upgrade_btn:
                btn_class = upgrade_btn.get_attribute('class') or ''
                info['can_upgrade'] = 'disabled' not in btn_class

            return info
        except:
            return None

    def upgrade_building(self, building_id: int) -> bool:
        """Navigate to building and click upgrade"""
        try:
            self.navigate_to_building(building_id)

            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')

            if not upgrade_btn:
                return False

            btn_class = upgrade_btn.get_attribute('class') or ''
            if 'disabled' in btn_class:
                return False

            upgrade_btn.click()
            return True

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False

    def auto_upgrade_resources(self, session) -> bool:
        """Auto-upgrade ONE field - returns True if upgraded"""
        # Priority order: croplands first, then others
        priority_fields = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 13, 14, 15, 16, 17, 18]

        for field_id in priority_fields:
            self.navigate_to_building(field_id)

            # Check current level
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

            # Skip if already at target level
            if level >= self.target_level:
                continue

            # Find upgrade button
            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')

            if not upgrade_btn:
                continue

            btn_class = upgrade_btn.get_attribute('class') or ''

            if 'disabled' in btn_class:
                continue

            # Click upgrade
            print(f"🔨 {name} L{level} -> L{level+1}")
            upgrade_btn.click()
            return True

        return False

    def auto_upgrade_all_to_20(self, session, stop_callback=None) -> int:
        """
        Continuously upgrade ALL resource fields to level 20.
        Keeps going until all fields are level 20 or no upgrades available.
        stop_callback: optional callable that returns True to stop
        """
        print("=" * 50)
        print(f"🚀 AUTO UPGRADE ALL RESOURCES TO LEVEL {self.target_level}")
        print("=" * 50)
        print("Press Q/S to stop\n")

        total_upgrades = 0
        rounds = 0

        # Default stop callback that never stops
        if stop_callback is None:
            stop_callback = lambda: False

        try:
            while not stop_callback():
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                # Check if all fields are at target level
                all_done = True
                fields_status = []

                for field_id in range(1, 19):
                    if stop_callback():
                        break
                    self.navigate_to_building(field_id)

                    h1 = self.browser.find_element(By.CSS_SELECTOR, 'h1.titleInHeader', timeout=2)
                    level = 0
                    name = f"#{field_id}"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()[:10]
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))

                    if level < self.target_level:
                        all_done = False

                    fields_status.append((field_id, name, level))

                if stop_callback():
                    break

                # Print status every 10 rounds
                if rounds % 10 == 1:
                    print("\nField Status:")
                    for fid, fname, flevel in fields_status:
                        status = "✓" if flevel >= self.target_level else f"L{flevel}"
                        print(f"  #{fid:2d} {fname:<12} {status}")

                if all_done:
                    print(f"\n🎉 ALL FIELDS AT LEVEL {self.target_level}!")
                    break

                # Upgrade as many as possible in this round
                upgraded_this_round = 0

                for field_id in range(1, 19):
                    if stop_callback():
                        break
                    self.navigate_to_building(field_id)

                    # Get level
                    h1 = self.browser.find_element(By.CSS_SELECTOR, 'h1.titleInHeader', timeout=2)
                    level = 0
                    name = f"Field #{field_id}"

                    if h1:
                        text = h1.text
                        if 'Level' in text:
                            name = text.split('Level')[0].strip()
                            match = re.search(r'Level\s*(\d+)', text)
                            if match:
                                level = int(match.group(1))

                    if level >= self.target_level:
                        continue

                    # Try to upgrade
                    upgrade_btn = self.browser.find_element(By.CSS_SELECTOR, 'button.build', timeout=2)

                    if not upgrade_btn:
                        continue

                    btn_class = upgrade_btn.get_attribute('class') or ''

                    if 'disabled' in btn_class:
                        continue

                    print(f"🔨 {name} L{level} -> L{level+1}")
                    upgrade_btn.click()
                    time.sleep(0.2)

                    total_upgrades += 1
                    upgraded_this_round += 1

                print(f"Upgraded {upgraded_this_round} fields this round")
                print(f"Total upgrades: {total_upgrades}")
                print("[Press Q/S to stop]")

                if upgraded_this_round == 0:
                    print("No upgrades available, waiting 5s...")
                    for _ in range(5):
                        if stop_callback():
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user")

        print(f"\n{'='*50}")
        print(f"✓ Total upgrades performed: {total_upgrades}")
        print(f"{'='*50}")

        return total_upgrades

    def is_queue_full(self) -> bool:
        return False

    def find_building_by_name(self, name: str) -> List[Dict]:
        """Find all buildings matching a name (partial match)"""
        name_lower = name.lower()
        matches = []

        # Scan resource fields (1-18)
        for field_id in range(1, 19):
            info = self.get_building_info(field_id)
            if info and name_lower in info['name'].lower():
                matches.append(info)

        # Scan village buildings (19-40)
        for building_id in range(19, 41):
            info = self.get_building_info(building_id)
            if info and info['name'] != 'Unknown' and name_lower in info['name'].lower():
                matches.append(info)

        return matches

    def upgrade_to_level(self, building_id: int, target_level: int, stop_callback=None) -> Dict:
        """
        Upgrade a specific building to a target level.
        Returns dict with results: upgrades performed, final level, success status
        stop_callback: optional callable that returns True to stop
        """
        result = {
            'building_id': building_id,
            'target_level': target_level,
            'start_level': 0,
            'final_level': 0,
            'upgrades': 0,
            'success': False,
            'message': ''
        }

        # Default stop callback that never stops
        if stop_callback is None:
            stop_callback = lambda: False

        try:
            # Get initial info
            info = self.get_building_info(building_id)
            if not info:
                result['message'] = f"Could not find building #{building_id}"
                return result

            result['start_level'] = info['level']
            result['building_name'] = info['name']

            print(f"\n🎯 Upgrading {info['name']} from L{info['level']} to L{target_level}")
            print("=" * 50)
            print("Press Q/S to stop\n")

            if info['level'] >= target_level:
                result['final_level'] = info['level']
                result['success'] = True
                result['message'] = f"{info['name']} is already at level {info['level']}"
                print(f"✓ {result['message']}")
                return result

            # Upgrade loop
            while not stop_callback():
                self.navigate_to_building(building_id)

                # Get current level
                h1 = self.browser.find_element(By.CSS_SELECTOR, 'h1.titleInHeader', timeout=2)
                current_level = 0
                if h1:
                    match = re.search(r'Level\s*(\d+)', h1.text)
                    if match:
                        current_level = int(match.group(1))

                result['final_level'] = current_level

                if current_level >= target_level:
                    result['success'] = True
                    result['message'] = f"Reached level {current_level}!"
                    print(f"\n🎉 {info['name']} reached level {current_level}!")
                    break

                # Try to upgrade
                upgrade_btn = self.browser.find_element(By.CSS_SELECTOR, 'button.build', timeout=2)

                if not upgrade_btn:
                    print("  Waiting for upgrade button... [Q/S to stop]")
                    for _ in range(2):
                        if stop_callback():
                            break
                        time.sleep(1)
                    continue

                btn_class = upgrade_btn.get_attribute('class') or ''

                if 'disabled' in btn_class:
                    print(f"  L{current_level} - Waiting for resources/queue... [Q/S to stop]")
                    for _ in range(3):
                        if stop_callback():
                            break
                        time.sleep(1)
                    continue

                # Click upgrade
                print(f"🔨 {info['name']} L{current_level} -> L{current_level + 1}")
                upgrade_btn.click()
                result['upgrades'] += 1
                time.sleep(0.3)

        except KeyboardInterrupt:
            result['message'] = "Stopped by user"
            print(f"\n⚠️  Stopped at level {result['final_level']}")

        except Exception as e:
            result['message'] = str(e)
            print(f"\n✗ Error: {e}")

        print(f"\n{'='*50}")
        print(f"✓ Performed {result['upgrades']} upgrades")
        print(f"  {info['name']}: L{result['start_level']} -> L{result['final_level']}")
        print(f"{'='*50}")

        return result

    def scan_all_fields(self) -> List[Dict]:
        """Scan all resource fields"""
        print("🔍 Scanning all resource fields...")
        fields = []

        for field_id in range(1, 19):
            info = self.get_building_info(field_id)
            if info:
                status = "✓" if info['level'] >= self.target_level else f"L{info['level']}"
                print(f"  #{field_id}: {info['name']} {status}")
                fields.append(info)

        return fields

    def auto_upgrade_village_building(self, session) -> bool:
        """Auto-upgrade ONE village building - returns True if upgraded"""
        # Priority order based on BUILDING_PRIORITIES
        buildings_with_priority = []

        for building_id in range(19, 41):
            self.navigate_to_building(building_id)

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
                elif text.strip() and 'Construct' not in text:
                    name = text.strip()

            # Skip empty slots or already maxed buildings
            if name == 'Empty' or name == 'Unknown' or 'Construct' in name:
                continue
            if level >= self.target_level:
                continue

            # Get priority (default 50 if not in list)
            priority = self.BUILDING_PRIORITIES.get(name, 50)
            buildings_with_priority.append((building_id, name, level, priority))

        # Sort by priority (highest first)
        buildings_with_priority.sort(key=lambda x: x[3], reverse=True)

        # Try to upgrade highest priority building
        for building_id, name, level, priority in buildings_with_priority:
            self.navigate_to_building(building_id)

            upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
            if not upgrade_btn:
                continue

            btn_class = upgrade_btn.get_attribute('class') or ''
            if 'disabled' in btn_class:
                continue

            print(f"🏗️ {name} L{level} -> L{level+1}")
            upgrade_btn.click()
            return True

        return False

    def scan_village_buildings(self) -> List[Dict]:
        """Scan all village buildings (19-40)"""
        print("🔍 Scanning village buildings...")
        buildings = []

        for building_id in range(19, 41):
            info = self.get_building_info(building_id)
            if info and info['name'] != 'Unknown' and info['name'] != 'Empty':
                status = "✓" if info['level'] >= self.target_level else f"L{info['level']}"
                print(f"  #{building_id}: {info['name']} {status}")
                buildings.append(info)

        return buildings

    def auto_upgrade_all_buildings(self, session, stop_callback=None) -> int:
        """
        Continuously upgrade ALL village buildings to max level.
        Keeps going until all buildings are at max level or no upgrades available.
        stop_callback: optional callable that returns True to stop
        """
        print("=" * 50)
        print(f"🏗️ AUTO UPGRADE ALL VILLAGE BUILDINGS TO LEVEL {self.target_level}")
        print("=" * 50)
        print("Press Q/S to stop\n")

        total_upgrades = 0
        rounds = 0

        # Default stop callback that never stops
        if stop_callback is None:
            stop_callback = lambda: False

        try:
            while not stop_callback():
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                # Check status of all buildings
                all_done = True
                buildings_status = []

                for building_id in range(19, 41):
                    if stop_callback():
                        break
                    self.navigate_to_building(building_id)

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

                    if name not in ['Empty', 'Unknown'] and 'Construct' not in name:
                        if level < self.target_level:
                            all_done = False
                        buildings_status.append((building_id, name, level))

                if stop_callback():
                    break

                # Print status every 5 rounds
                if rounds % 5 == 1:
                    print("\nBuilding Status:")
                    for bid, bname, blevel in buildings_status:
                        status = "✓" if blevel >= self.target_level else f"L{blevel}"
                        print(f"  #{bid:2d} {bname:<18} {status}")

                if all_done:
                    print(f"\n🎉 ALL BUILDINGS AT LEVEL {self.target_level}!")
                    break

                # Upgrade as many as possible
                upgraded_this_round = 0

                for building_id, name, level in buildings_status:
                    if stop_callback():
                        break
                    if level >= self.target_level:
                        continue

                    self.navigate_to_building(building_id)

                    upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                    if not upgrade_btn:
                        continue

                    btn_class = upgrade_btn.get_attribute('class') or ''
                    if 'disabled' in btn_class:
                        continue

                    print(f"🏗️ {name} L{level} -> L{level+1}")
                    upgrade_btn.click()
                    time.sleep(0.2)

                    total_upgrades += 1
                    upgraded_this_round += 1

                print(f"Upgraded {upgraded_this_round} buildings this round")
                print(f"Total upgrades: {total_upgrades}")
                print("[Press Q/S to stop]")

                if upgraded_this_round == 0:
                    print("No upgrades available, waiting 5s...")
                    for _ in range(5):
                        if stop_callback():
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user")

        print(f"\n{'='*50}")
        print(f"✓ Total building upgrades: {total_upgrades}")
        print(f"{'='*50}")

        return total_upgrades

    # ==================== SMART BUILD ORDER ====================

    # Building GIDs for construction (Travian building type IDs)
    BUILDING_GIDS = {
        'Woodcutter': 1,
        'Clay Pit': 2,
        'Iron Mine': 3,
        'Cropland': 4,
        'Sawmill': 5,
        'Brickyard': 6,
        'Iron Foundry': 7,
        'Grain Mill': 8,
        'Bakery': 9,
        'Warehouse': 10,
        'Granary': 11,
        'Smithy': 13,
        'Tournament Square': 14,
        'Main Building': 15,
        'Rally Point': 16,
        'Marketplace': 17,
        'Embassy': 18,
        'Barracks': 19,
        'Stable': 20,
        'Workshop': 21,
        'Academy': 22,
        'Cranny': 23,
        'Town Hall': 24,
        'Residence': 25,
        'Palace': 26,
        'Treasury': 27,
        'Trade Office': 28,
        'Great Barracks': 29,
        'Great Stable': 30,
        'City Wall': 31,
        'Earth Wall': 32,
        'Palisade': 33,
        'Stonemason': 34,
        'Brewery': 35,
        'Trapper': 36,
        'Hero Mansion': 37,
        'Great Warehouse': 38,
        'Great Granary': 39,
        'Horse Drinking Trough': 41,
    }

    # Building prerequisites: building_name -> [(prereq_name, prereq_level), ...]
    BUILDING_PREREQUISITES = {
        'Cranny': [],
        'Embassy': [],
        'Warehouse': [],
        'Granary': [],
        'Barracks': [('Rally Point', 1), ('Main Building', 3)],
        'Hero Mansion': [('Rally Point', 1), ('Main Building', 3)],
        'Marketplace': [('Warehouse', 1), ('Granary', 1), ('Main Building', 3)],
        'Academy': [('Barracks', 3), ('Main Building', 3)],
        'Smithy': [('Academy', 1), ('Main Building', 3)],
        'Stable': [('Smithy', 3), ('Academy', 5)],
        'Workshop': [('Academy', 10), ('Main Building', 5)],
        'Town Hall': [('Academy', 10), ('Main Building', 10)],
        'Palace': [('Embassy', 1), ('Main Building', 5)],
        'Residence': [('Main Building', 5)],
        'Grain Mill': [('Cropland', 5)],
        'Sawmill': [('Woodcutter', 10), ('Main Building', 5)],
        'Brickyard': [('Clay Pit', 10), ('Main Building', 5)],
        'Iron Foundry': [('Iron Mine', 10), ('Main Building', 5)],
        'Bakery': [('Cropland', 10), ('Main Building', 5), ('Grain Mill', 5)],
        'Tournament Square': [('Rally Point', 15)],
        'Trade Office': [('Marketplace', 20), ('Stable', 10)],
        'Treasury': [('Main Building', 10)],
        'Stonemason': [('Palace', 3), ('Main Building', 5)],
        'Horse Drinking Trough': [('Stable', 20), ('Rally Point', 10)],
    }

    # Ordered build sequence respecting prerequisites
    # Each entry: (building_name, allow_duplicates)
    AUTO_BUILD_ORDER = [
        # Phase 1: No prerequisites
        ('Cranny', True),
        ('Warehouse', True),
        ('Granary', True),
        ('Embassy', False),
        # Phase 2: Need Main Building L3 + Rally Point L1
        ('Barracks', False),
        ('Hero Mansion', False),
        ('Marketplace', False),
        # Phase 3: Need Barracks L3
        ('Academy', False),
        # Phase 4: Need Academy L1
        ('Smithy', False),
        # Phase 5: Need Academy L5 + Smithy L3
        ('Stable', False),
        # Phase 6: Advanced buildings (need higher levels)
        ('Workshop', False),
        ('Town Hall', False),
        ('Palace', False),
        # Phase 7: Production boosters (need resource fields L10)
        ('Grain Mill', False),
        ('Sawmill', False),
        ('Brickyard', False),
        ('Iron Foundry', False),
        ('Bakery', False),
        # Phase 8: Late-game buildings
        ('Tournament Square', False),
        ('Trade Office', False),
        ('Treasury', False),
    ]

    def _get_field_level(self, field_id: int):
        """Quick helper: navigate and return (name, level)"""
        self.navigate_to_building(field_id)
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
            elif text.strip():
                name = text.strip()
        return name, level

    def _try_upgrade(self, building_id: int) -> bool:
        """Try to click the upgrade button on the current page. Returns True if clicked."""
        self.navigate_to_building(building_id)
        upgrade_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
        if not upgrade_btn:
            return False
        btn_class = upgrade_btn.get_attribute('class') or ''
        if 'disabled' in btn_class:
            return False
        upgrade_btn.click()
        return True

    def _find_building_slot_by_name(self, name: str) -> Optional[int]:
        """Find the slot ID of an existing building by name"""
        name_lower = name.lower()
        for building_id in range(19, 41):
            self.navigate_to_building(building_id)
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                text = h1.text
                bname = text.split('Level')[0].strip() if 'Level' in text else text.strip()
                if name_lower in bname.lower():
                    return building_id
        return None

    def _find_empty_slot(self) -> Optional[int]:
        """Find the first empty building slot (19-40)"""
        from config import config
        for slot_id in range(19, 41):
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
            url = self.browser.driver.current_url
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            h1_text = h1.text.strip() if h1 else ''

            if 'construct' in url.lower() or h1_text in ['', 'Unknown'] or 'Construct' in h1_text:
                return slot_id
        return None

    def _check_prerequisites(self, building_name: str) -> tuple:
        """
        Check if all prerequisites for a building are met.
        Returns (all_met: bool, missing: list of (name, required_level, current_level))
        """
        prereqs = self.BUILDING_PREREQUISITES.get(building_name, [])
        if not prereqs:
            return True, []

        missing = []
        for prereq_name, prereq_level in prereqs:
            slot = self._find_building_slot_by_name(prereq_name)
            if not slot:
                missing.append((prereq_name, prereq_level, 0))
            else:
                _, current_level = self._get_field_level(slot)
                if current_level < prereq_level:
                    missing.append((prereq_name, prereq_level, current_level))

        return len(missing) == 0, missing

    def _upgrade_building_to_level(self, building_name: str, target_level: int, stop_callback) -> bool:
        """Upgrade a building to target level. Returns True if reached."""
        slot = self._find_building_slot_by_name(building_name)
        if not slot:
            return False

        while not stop_callback():
            name, level = self._get_field_level(slot)
            if level >= target_level:
                return True
            if self._try_upgrade(slot):
                print(f"    🔧 {name} L{level} -> L{level+1}")
            else:
                # Can't upgrade right now, wait
                for _ in range(3):
                    if stop_callback():
                        return False
                    time.sleep(1)
                # Check again
                _, level = self._get_field_level(slot)
                if level >= target_level:
                    return True
                return False  # Still can't upgrade
        return False

    def _build_new_building(self, slot_id: int, building_name: str) -> bool:
        """Try to construct a new building in an empty slot."""
        from config import config

        gid = self.BUILDING_GIDS.get(building_name)
        if not gid:
            print(f"  Unknown building GID: {building_name}")
            return False

        # Method 1: Direct URL navigation with GID parameter
        # This is the most reliable method for Travian
        direct_url = f"{config.base_url}/build.php?id={slot_id}&gid={gid}"
        self.browser.navigate_to(direct_url)
        time.sleep(0.5)

        # Check if we're on the building page and can build
        build_btn = self.browser.find_element_fast(By.CSS_SELECTOR,
            'button.build, button.green, input.build, input[type="submit"].green, .contractLink button, .contractBuilding button')
        if build_btn:
            btn_class = build_btn.get_attribute('class') or ''
            btn_disabled = build_btn.get_attribute('disabled')
            if 'disabled' not in btn_class and not btn_disabled:
                try:
                    build_btn.click()
                    print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                    time.sleep(0.5)
                    return True
                except:
                    pass

        # Method 2: Look for "Construct" or build contract on the page
        contract_selectors = [
            '.contractLink a',
            '.contractBuilding a',
            'a.build',
            '.green.build',
            'button.textButtonV1.green',
            'form button[type="submit"]',
        ]
        for sel in contract_selectors:
            btn = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if btn:
                try:
                    btn_class = btn.get_attribute('class') or ''
                    if 'disabled' not in btn_class:
                        btn.click()
                        print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                        time.sleep(0.5)
                        return True
                except:
                    continue

        # Method 3: Navigate to construction list and click through tabs
        self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
        time.sleep(0.5)

        # Building categories in Travian - try clicking each tab
        # Categories: Infrastructure, Military, Resources
        category_selectors = [
            # Tab containers
            '.tabContainer a',
            '.tabContainer button',
            '.tabs a',
            '.tabs button',
            '.contentNavi a',
            '.contentNavi button',
            # Filter buttons
            '.buildingFilter a',
            '.buildingFilter button',
            '.filter a',
            '.filter button',
            # Navigation
            'nav a',
            '.buildingCategories a',
            '.buildingList .header a',
            # Category divs that might be clickable
            '.category',
            '.infrastructureBuildings',
            '.militaryBuildings',
            '.resourceBuildings',
        ]

        # First try without clicking tabs
        if self._try_find_and_build(gid, building_name, slot_id):
            return True

        # Try clicking each possible tab/category
        for cat_sel in category_selectors:
            try:
                tabs = self.browser.find_elements(By.CSS_SELECTOR, cat_sel)
                for tab in tabs:
                    try:
                        if tab.is_displayed():
                            # Click the tab
                            tab.click()
                            time.sleep(0.3)

                            # Try to find and build
                            if self._try_find_and_build(gid, building_name, slot_id):
                                return True
                    except:
                        continue
            except:
                continue

        # Method 4: Search page for building name and click
        try:
            page_source = self.browser.get_page_source().lower()
            if building_name.lower() in page_source:
                # Building name is on the page, try to find clickable element
                all_clickable = self.browser.find_elements(By.CSS_SELECTOR,
                    'a, button, div[onclick], span[onclick], .buildingWrapper, .building')
                for elem in all_clickable:
                    try:
                        text = elem.text.strip().lower() if elem.text else ''
                        if building_name.lower() in text:
                            elem.click()
                            time.sleep(0.3)
                            # Now look for build button
                            build_btn = self.browser.find_element_fast(By.CSS_SELECTOR,
                                'button.build, button.green, input.build')
                            if build_btn:
                                build_btn.click()
                                print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                                return True
                    except:
                        continue
        except:
            pass

        # Debug: dump available buildings on the page
        self._debug_construction_page(building_name, gid)
        return False

    def _debug_construction_page(self, building_name: str, gid: int):
        """Debug helper to show what buildings are available."""
        print(f"  DEBUG: Looking for {building_name} (GID {gid})")

        # Find all links with gid
        all_gid_links = self.browser.find_elements(By.CSS_SELECTOR, 'a[href*="gid="]')
        if all_gid_links:
            print(f"  DEBUG: Found {len(all_gid_links)} GID links on page:")
            for link in all_gid_links[:10]:  # Show first 10
                try:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()[:30] if link.text else ''
                    if text:
                        print(f"    - {text}: {href.split('gid=')[-1].split('&')[0] if 'gid=' in href else '?'}")
                except:
                    pass

        # Show current URL
        print(f"  DEBUG: Current URL: {self.browser.current_url}")

    def _try_find_and_build(self, gid: int, building_name: str, slot_id: int) -> bool:
        """Try to find a building by GID on current page and click build."""
        # Selectors to find building links
        gid_selectors = [
            f'a[href*="gid={gid}"]',
            f'a[href*="&gid={gid}"]',
            f'a[href*="?gid={gid}"]',
            f'.gid{gid} a',
            f'[data-gid="{gid}"] a',
            f'.building{gid}',
            f'#building{gid}',
        ]

        for selector in gid_selectors:
            try:
                links = self.browser.find_elements(By.CSS_SELECTOR, selector)
                for link in links:
                    if link.is_displayed():
                        link.click()
                        time.sleep(0.3)

                        # Look for build button on the new page
                        build_selectors = [
                            'button.build',
                            'button.green',
                            'input.build',
                            'input[type="submit"].green',
                            '.contractLink button',
                            'button.textButtonV1.green',
                            'form button[type="submit"]',
                        ]

                        for btn_sel in build_selectors:
                            build_btn = self.browser.find_element_fast(By.CSS_SELECTOR, btn_sel)
                            if build_btn:
                                btn_class = build_btn.get_attribute('class') or ''
                                btn_disabled = build_btn.get_attribute('disabled')
                                if 'disabled' not in btn_class and not btn_disabled:
                                    try:
                                        build_btn.click()
                                        print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                                        time.sleep(0.5)
                                        return True
                                    except:
                                        pass
            except:
                continue

        return False

    def _get_existing_building_names(self) -> set:
        """Get set of building names currently in the village (slots 19-40)"""
        names = set()
        for building_id in range(19, 41):
            bname, level = self._get_field_level(building_id)
            if bname not in ['Empty', 'Unknown', f'Field #{building_id}'] and 'Construct' not in bname:
                names.add(bname)
        return names

    def smart_build_order(self, stop_callback) -> int:
        """
        Smart build order with proper prerequisites:
        Phase 1: Upgrade Main Building to level 20
        Phase 2: Upgrade resource fields to level 10
        Phase 3: Build essential buildings (Warehouse, Granary, Rally Point)
        Phase 4: Build and upgrade buildings in dependency order
        Phase 5: Continue upgrading everything to level 20
        Returns total upgrades performed.
        """
        total = 0

        # ---- Phase 1: Main Building to level 20 ----
        print(f"\n{'='*50}")
        print(f"PHASE 1: Upgrade Main Building to level 20")
        print(f"{'='*50}")

        mb_slot = self._find_building_slot_by_name('Main Building')
        if mb_slot:
            while not stop_callback():
                name, level = self._get_field_level(mb_slot)
                if level >= 20:
                    print(f"  ✓ Main Building at level {level}")
                    break
                if self._try_upgrade(mb_slot):
                    print(f"  🏗️ Main Building L{level} -> L{level+1}")
                    total += 1
                else:
                    # Try upgrading a resource field instead while waiting
                    upgraded_resource = False
                    for field_id in range(1, 19):
                        if stop_callback():
                            break
                        fname, flevel = self._get_field_level(field_id)
                        if flevel < 20 and self._try_upgrade(field_id):
                            print(f"  🔨 {fname} L{flevel} -> L{flevel+1}")
                            total += 1
                            upgraded_resource = True
                            break
                    if not upgraded_resource:
                        print(f"  Waiting (3s)...")
                        for _ in range(3):
                            if stop_callback():
                                return total
                            time.sleep(1)
        else:
            print(f"  ✗ Main Building not found!")

        if stop_callback():
            return total

        # ---- Phase 2: Resource fields to level 10 ----
        print(f"\n{'='*50}")
        print(f"PHASE 2: Upgrade resource fields to level 10")
        print(f"{'='*50}")

        while not stop_callback():
            all_at_10 = True
            upgraded = False

            for field_id in range(1, 19):
                if stop_callback():
                    return total
                name, level = self._get_field_level(field_id)
                if level < 10:
                    all_at_10 = False
                    if self._try_upgrade(field_id):
                        print(f"  🔨 {name} L{level} -> L{level+1}")
                        total += 1
                        upgraded = True

            if all_at_10:
                print(f"  ✓ All resource fields at level 10+")
                break

            if not upgraded:
                print(f"  Waiting (3s)...")
                for _ in range(3):
                    if stop_callback():
                        return total
                    time.sleep(1)

        if stop_callback():
            return total

        # ---- Phase 3: Build essential buildings ----
        print(f"\n{'='*50}")
        print(f"PHASE 3: Build essential infrastructure")
        print(f"{'='*50}")

        essential_buildings = ['Warehouse', 'Granary', 'Cranny', 'Embassy']
        existing = self._get_existing_building_names()

        for building_name in essential_buildings:
            if stop_callback():
                return total

            allow_dup = building_name in ['Warehouse', 'Granary', 'Cranny']
            if not allow_dup and building_name in existing:
                print(f"  ✓ {building_name} already exists")
                continue

            empty_slot = self._find_empty_slot()
            if not empty_slot:
                print(f"  ✗ No empty slots for {building_name}")
                continue

            print(f"  Building {building_name}...")
            if self._build_new_building(empty_slot, building_name):
                existing.add(building_name)
                total += 1
                time.sleep(0.5)

        if stop_callback():
            return total

        # ---- Phase 4: Build and upgrade in dependency order ----
        print(f"\n{'='*50}")
        print(f"PHASE 4: Build buildings (respecting prerequisites)")
        print(f"{'='*50}")

        # Refresh existing buildings
        existing = self._get_existing_building_names()

        for building_name, allow_dup in self.AUTO_BUILD_ORDER:
            if stop_callback():
                return total

            # Skip if already exists (unless duplicates allowed)
            if not allow_dup and building_name in existing:
                continue

            # Skip essential buildings (already handled)
            if building_name in ['Warehouse', 'Granary', 'Cranny', 'Embassy']:
                continue

            # Check prerequisites
            prereqs_met, missing = self._check_prerequisites(building_name)

            if not prereqs_met:
                print(f"\n  📋 {building_name} needs prerequisites:")
                for prereq_name, req_level, cur_level in missing:
                    print(f"     - {prereq_name} L{req_level} (currently L{cur_level})")

                # Try to fulfill prerequisites
                all_fulfilled = True
                for prereq_name, req_level, cur_level in missing:
                    if stop_callback():
                        return total

                    # Check if prereq building exists
                    prereq_slot = self._find_building_slot_by_name(prereq_name)

                    if not prereq_slot:
                        # Need to build the prerequisite first
                        print(f"     Building {prereq_name} first...")
                        empty_slot = self._find_empty_slot()
                        if empty_slot:
                            if self._build_new_building(empty_slot, prereq_name):
                                existing.add(prereq_name)
                                total += 1
                                time.sleep(0.5)
                                prereq_slot = self._find_building_slot_by_name(prereq_name)
                            else:
                                print(f"     ✗ Could not build {prereq_name}")
                                all_fulfilled = False
                                continue

                    # Now upgrade the prereq to required level
                    if prereq_slot and cur_level < req_level:
                        print(f"     Upgrading {prereq_name} to L{req_level}...")
                        while not stop_callback():
                            _, level = self._get_field_level(prereq_slot)
                            if level >= req_level:
                                print(f"     ✓ {prereq_name} at L{level}")
                                break
                            if self._try_upgrade(prereq_slot):
                                print(f"     🔧 {prereq_name} L{level} -> L{level+1}")
                                total += 1
                            else:
                                # Try upgrading something else while waiting
                                for field_id in range(1, 19):
                                    fname, flevel = self._get_field_level(field_id)
                                    if flevel < 20 and self._try_upgrade(field_id):
                                        print(f"     🔨 {fname} L{flevel} -> L{flevel+1}")
                                        total += 1
                                        break
                                else:
                                    time.sleep(2)

                if not all_fulfilled:
                    print(f"  ✗ Skipping {building_name} (prerequisites not met)")
                    continue

            # Now try to build the building
            empty_slot = self._find_empty_slot()
            if not empty_slot:
                print(f"  ✗ No empty slots")
                break

            print(f"  Building {building_name}...")
            if self._build_new_building(empty_slot, building_name):
                existing.add(building_name)
                total += 1
                time.sleep(0.5)
            else:
                print(f"  ✗ Could not build {building_name}")

        if stop_callback():
            return total

        # ---- Phase 5: Upgrade everything to level 20 ----
        print(f"\n{'='*50}")
        print(f"PHASE 5: Upgrade everything to level 20")
        print(f"{'='*50}")

        while not stop_callback():
            all_done = True
            upgraded = False

            # Resources first
            for field_id in range(1, 19):
                if stop_callback():
                    return total
                name, level = self._get_field_level(field_id)
                if level < 20:
                    all_done = False
                    if self._try_upgrade(field_id):
                        print(f"  🔨 {name} L{level} -> L{level+1}")
                        total += 1
                        upgraded = True

            # Village buildings
            for building_id in range(19, 41):
                if stop_callback():
                    return total
                name, level = self._get_field_level(building_id)
                if name in ['Empty', 'Unknown'] or 'Construct' in name:
                    continue
                if level < 20:
                    all_done = False
                    if self._try_upgrade(building_id):
                        print(f"  🏗️ {name} L{level} -> L{level+1}")
                        total += 1
                        upgraded = True

            if all_done:
                print(f"\n  🎉 Everything at level 20!")
                break

            if not upgraded:
                print(f"  Waiting (5s)...")
                for _ in range(5):
                    if stop_callback():
                        return total
                    time.sleep(1)

        return total
