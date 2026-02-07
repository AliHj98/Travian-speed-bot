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

    def demolish_building(self, building_id: int, building_name: str = None) -> bool:
        """Demolish a building by ID (uses dropdown in Main Building)"""
        from config import config

        try:
            # Find Main Building slot
            mb_slot = None
            for slot_id in range(19, 41):
                self.navigate_to_building(slot_id)
                h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
                if h1 and 'main' in h1.text.lower() and 'building' in h1.text.lower():
                    mb_slot = slot_id
                    break

            if not mb_slot:
                print("  ✗ Main Building not found")
                return False

            # Navigate to Main Building (demolish is usually on a tab or the main page)
            self.browser.navigate_to(f"{config.base_url}/build.php?id={mb_slot}")
            time.sleep(0.3)

            # Look for demolish tab/link and click it
            demolish_tab_selectors = [
                'a[href*="t=2"]',
                'a[href*="demolish"]',
                '.tabContainer a:last-child',
                'nav a:last-child',
                'a.demolishTab',
            ]

            for sel in demolish_tab_selectors:
                tab = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if tab:
                    try:
                        tab.click()
                        time.sleep(0.3)
                        break
                    except:
                        continue

            # Find the dropdown/select element
            dropdown_selectors = [
                'select',
                'select[name*="demolish"]',
                'select[name*="building"]',
                '#demolish select',
                '.demolish select',
            ]

            dropdown = None
            for sel in dropdown_selectors:
                dropdown = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if dropdown:
                    break

            if not dropdown:
                print("  ✗ Demolish dropdown not found")
                return False

            # Select the building from dropdown
            from selenium.webdriver.support.ui import Select
            select = Select(dropdown)

            # Try to select by value (building ID)
            selected = False
            try:
                select.select_by_value(str(building_id))
                selected = True
            except:
                pass

            # Try to select by visible text (building name)
            if not selected and building_name:
                try:
                    for option in select.options:
                        option_text = option.text.lower().replace(' ', '')
                        if building_name.lower().replace(' ', '') in option_text:
                            select.select_by_visible_text(option.text)
                            selected = True
                            break
                except:
                    pass

            # Try to find option containing the building ID
            if not selected:
                try:
                    for option in select.options:
                        option_val = option.get_attribute('value') or ''
                        if str(building_id) in option_val:
                            select.select_by_value(option_val)
                            selected = True
                            break
                except:
                    pass

            if not selected:
                print(f"  ✗ Could not find building #{building_id} in dropdown")
                return False

            # Click the demolish button
            demolish_btn_selectors = [
                'button[type="submit"]',
                'button.green',
                'button.demolish',
                'input[type="submit"]',
                '.demolish button',
            ]

            for sel in demolish_btn_selectors:
                btn = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if btn:
                    btn_text = btn.text.lower() if btn.text else ''
                    btn_value = btn.get_attribute('value') or ''
                    # Make sure it's a demolish button
                    if 'demolish' in btn_text or 'demolish' in btn_value.lower() or 'green' in (btn.get_attribute('class') or ''):
                        btn.click()
                        print(f"  ✓ Demolishing building #{building_id}")
                        return True

            print(f"  ✗ Could not find demolish button")
            return False

        except Exception as e:
            print(f"  ✗ Demolish error: {e}")
            return False

    def demolish_by_name(self, building_name: str) -> bool:
        """Demolish a building by name"""
        # First find the building slot
        building_name_lower = building_name.lower().replace(' ', '')

        for slot_id in range(19, 41):
            self.navigate_to_building(slot_id)
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                h1_text = h1.text.lower().replace(' ', '')
                if building_name_lower in h1_text:
                    print(f"  Found {building_name} at slot #{slot_id}")
                    return self.demolish_building(slot_id, building_name)

        print(f"  ✗ Building '{building_name}' not found")
        return False

    def demolish_all_of_type(self, building_name: str, stop_callback=None) -> int:
        """Demolish all buildings of a specific type"""
        if stop_callback is None:
            stop_callback = lambda: False

        building_name_lower = building_name.lower().replace(' ', '')
        demolished = 0

        # Find all matching buildings
        matching_slots = []
        for slot_id in range(19, 41):
            if stop_callback():
                break
            self.navigate_to_building(slot_id)
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                h1_text = h1.text.lower().replace(' ', '')
                if building_name_lower in h1_text:
                    matching_slots.append((slot_id, h1.text.split('Level')[0].strip()))

        print(f"  Found {len(matching_slots)} {building_name}(s) to demolish")

        for slot_id, name in matching_slots:
            if stop_callback():
                break
            if self.demolish_building(slot_id, name):
                demolished += 1
                time.sleep(0.5)  # Small delay between demolitions

        return demolished

    def scan_and_demolish_menu(self) -> List[Dict]:
        """Scan village buildings and return list for demolish selection"""
        buildings = []
        for slot_id in range(19, 41):
            self.navigate_to_building(slot_id)
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                text = h1.text
                name = "Empty"
                level = 0
                if 'Level' in text:
                    name = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        level = int(match.group(1))
                elif text.strip() and 'Construct' not in text:
                    name = text.strip()

                if name not in ['Empty', 'Unknown'] and 'Construct' not in name:
                    buildings.append({
                        'slot': slot_id,
                        'name': name,
                        'level': level
                    })
        return buildings

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
                    # No upgrades available - all done or waiting for resources
                    break

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
                    # No upgrade button, done
                    break

                btn_class = upgrade_btn.get_attribute('class') or ''

                if 'disabled' in btn_class:
                    # Can't upgrade, done for now
                    break

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
                    # No upgrades available - all done or waiting for resources
                    break

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
                # Can't upgrade right now, done for now
                return False
        return False

    def _build_new_building(self, slot_id: int, building_name: str) -> bool:
        """Try to construct a new building in an empty slot."""
        from config import config

        gid = self.BUILDING_GIDS.get(building_name)
        if not gid:
            print(f"  Unknown building GID: {building_name}")
            return False

        building_name_lower = building_name.lower().replace(' ', '')

        # Method 1: Navigate to empty slot first
        self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
        time.sleep(0.3)

        # Method 2: Find h2 with building name, then click sibling "Build" button
        # Structure: <div class="buildingWrapper"><h2>Barracks</h2>...<button>Build the building</button></div>
        h2_elements = self.browser.find_elements(By.CSS_SELECTOR, 'h2')
        for h2 in h2_elements:
            try:
                h2_text = h2.text.strip().lower().replace(' ', '') if h2.text else ''
                # Exact match (normalized)
                if h2_text == building_name_lower:
                    # Found the building! Now find the build button in the same container
                    parent = h2.find_element(By.XPATH, './..')  # Get parent element

                    # Try to find build button in parent or nearby
                    build_btn = None
                    try:
                        build_btn = parent.find_element(By.CSS_SELECTOR, 'button.green, button.build, .contractLink button')
                    except:
                        pass

                    if not build_btn:
                        # Try grandparent
                        try:
                            grandparent = parent.find_element(By.XPATH, './..')
                            build_btn = grandparent.find_element(By.CSS_SELECTOR, 'button.green, button.build, .contractLink button')
                        except:
                            pass

                    if build_btn:
                        btn_class = build_btn.get_attribute('class') or ''
                        if 'disabled' not in btn_class:
                            build_btn.click()
                            print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                            return True
            except:
                continue

        # Method 3: Try direct URL with GID
        direct_url = f"{config.base_url}/build.php?id={slot_id}&gid={gid}"
        self.browser.navigate_to(direct_url)
        time.sleep(0.3)

        # Look for build button
        build_selectors = [
            'button.green:not(.disabled)',
            'button.build:not(.disabled)',
            '.contractLink button',
            'form button.green',
        ]

        for btn_sel in build_selectors:
            build_btn = self.browser.find_element_fast(By.CSS_SELECTOR, btn_sel)
            if build_btn:
                btn_class = build_btn.get_attribute('class') or ''
                if 'disabled' not in btn_class:
                    try:
                        build_btn.click()
                        print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                        return True
                    except:
                        pass

        # Debug: dump available buildings on the page
        self._debug_construction_page(building_name, gid)
        return False

    def _debug_construction_page(self, building_name: str, gid: int):
        """Debug helper to show what buildings are available."""
        print(f"  DEBUG: Looking for {building_name} (GID {gid})")
        print(f"  DEBUG: Current URL: {self.browser.current_url}")

        # Find all links with gid
        all_gid_links = self.browser.find_elements(By.CSS_SELECTOR, 'a[href*="gid="]')
        if all_gid_links:
            print(f"  DEBUG: Found {len(all_gid_links)} building links:")
            for link in all_gid_links[:15]:
                try:
                    href = link.get_attribute('href') or ''
                    text = link.text.strip()[:30] if link.text else ''
                    gid_val = href.split('gid=')[-1].split('&')[0] if 'gid=' in href else '?'
                    if text:
                        print(f"    - '{text}' (GID {gid_val})")
                except:
                    pass

        # Find h2 elements (building names are in h2)
        h2_elements = self.browser.find_elements(By.CSS_SELECTOR, 'h2, h2 a')
        if h2_elements:
            print(f"  DEBUG: Found {len(h2_elements)} h2 elements:")
            for elem in h2_elements[:15]:
                try:
                    text = elem.text.strip()[:40] if elem.text else '[no text]'
                    href = elem.get_attribute('href') or ''
                    if text:
                        print(f"    - '{text}' {href[-30:] if href else ''}")
                except:
                    pass

        # Find clickable elements with building-related classes
        building_elements = self.browser.find_elements(By.CSS_SELECTOR, '.buildingWrapper, .contractLink, .building, .newBuilding')
        if building_elements:
            print(f"  DEBUG: Found {len(building_elements)} building elements:")
            for elem in building_elements[:10]:
                try:
                    text = elem.text.strip()[:40] if elem.text else '[no text]'
                    print(f"    - '{text}'")
                except:
                    pass

        # Show tabs/categories if any
        tabs = self.browser.find_elements(By.CSS_SELECTOR, '.tabContainer a, .tabs a, .contentNavi a, nav a')
        if tabs:
            print(f"  DEBUG: Found {len(tabs)} category tabs:")
            for i, tab in enumerate(tabs[:5]):
                try:
                    text = tab.text.strip()[:20] if tab.text else f'[tab {i}]'
                    print(f"    - Tab {i}: '{text}'")
                except:
                    pass

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

    def _scan_village_buildings(self) -> Dict[int, Dict]:
        """
        Scan all village building slots (19-40) once and cache the results.
        Returns dict: slot_id -> {name, level, is_empty}
        """
        print("🔍 Scanning village buildings once...")
        cache = {}
        for slot_id in range(19, 41):
            name, level = self._get_field_level(slot_id)
            is_empty = name in ['Empty', 'Unknown', f'Field #{slot_id}'] or 'Construct' in name
            cache[slot_id] = {'name': name, 'level': level, 'is_empty': is_empty}
            if not is_empty:
                print(f"  #{slot_id}: {name} L{level}")
            else:
                print(f"  #{slot_id}: (empty)")
        return cache

    def _find_slot_by_name_cached(self, name: str, cache: Dict[int, Dict]) -> Optional[int]:
        """Find the slot ID of an existing building by name using cache (fuzzy match)."""
        # Remove spaces and lowercase for comparison
        name_normalized = name.lower().replace(' ', '').replace('-', '')
        for slot_id, info in cache.items():
            if not info['is_empty']:
                info_normalized = info['name'].lower().replace(' ', '').replace('-', '')
                # Check if names match (fuzzy)
                if name_normalized in info_normalized or info_normalized in name_normalized:
                    return slot_id
        return None

    def _find_empty_slot_cached(self, cache: Dict[int, Dict]) -> Optional[int]:
        """Find the first empty building slot using cache."""
        for slot_id in range(19, 41):
            if cache[slot_id]['is_empty']:
                return slot_id
        return None

    def _get_existing_names_cached(self, cache: Dict[int, Dict]) -> set:
        """Get set of building names currently in the village using cache (normalized)."""
        names = set()
        for slot_id, info in cache.items():
            if not info['is_empty']:
                # Add both original and normalized names
                names.add(info['name'])
                names.add(info['name'].lower().replace(' ', '').replace('-', ''))
        return names

    def _building_exists(self, name: str, cache: Dict[int, Dict]) -> bool:
        """Check if a building exists (fuzzy match)."""
        return self._find_slot_by_name_cached(name, cache) is not None

    def _check_prerequisites_cached(self, building_name: str, cache: Dict[int, Dict]) -> tuple:
        """
        Check if all prerequisites for a building are met using cache.
        Returns (all_met: bool, missing: list of (name, required_level, current_level))
        """
        prereqs = self.BUILDING_PREREQUISITES.get(building_name, [])
        if not prereqs:
            return True, []

        missing = []
        for prereq_name, prereq_level in prereqs:
            slot = self._find_slot_by_name_cached(prereq_name, cache)
            if not slot:
                missing.append((prereq_name, prereq_level, 0))
            else:
                current_level = cache[slot]['level']
                if current_level < prereq_level:
                    missing.append((prereq_name, prereq_level, current_level))

        return len(missing) == 0, missing

    def _update_cache(self, slot_id: int, cache: Dict[int, Dict], force_not_empty: bool = False):
        """Update a single slot in the cache after building/upgrading."""
        name, level = self._get_field_level(slot_id)
        is_empty = name in ['Empty', 'Unknown', f'Field #{slot_id}'] or 'Construct' in name
        # If we just built something there, force it to not be empty
        if force_not_empty:
            is_empty = False
        cache[slot_id] = {'name': name, 'level': level, 'is_empty': is_empty}

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

        # ---- SCAN ONCE: Cache all village building slots ----
        print(f"\n{'='*50}")
        print(f"INITIAL SCAN: Caching village buildings")
        print(f"{'='*50}")
        village_cache = self._scan_village_buildings()

        if stop_callback():
            return total

        # ---- Phase 1: Main Building to level 20 ----
        print(f"\n{'='*50}")
        print(f"PHASE 1: Upgrade Main Building to level 20")
        print(f"{'='*50}")

        mb_slot = self._find_slot_by_name_cached('Main Building', village_cache)
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
                        # No upgrades available, move on
                        break
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
                # No upgrades available, move on
                break

        if stop_callback():
            return total

        # ---- Phase 3: Build essential buildings ----
        print(f"\n{'='*50}")
        print(f"PHASE 3: Build essential infrastructure")
        print(f"{'='*50}")

        essential_buildings = ['Warehouse', 'Granary', 'Cranny', 'Embassy']
        existing = self._get_existing_names_cached(village_cache)

        for building_name in essential_buildings:
            if stop_callback():
                return total

            allow_dup = building_name in ['Warehouse', 'Granary', 'Cranny']
            if not allow_dup and building_name in existing:
                print(f"  ✓ {building_name} already exists")
                continue

            empty_slot = self._find_empty_slot_cached(village_cache)
            if not empty_slot:
                print(f"  ✗ No empty slots for {building_name}")
                continue

            print(f"  Building {building_name}...")
            if self._build_new_building(empty_slot, building_name):
                existing.add(building_name)
                total += 1
                # Update cache - mark slot as NOT empty since we just built there
                self._update_cache(empty_slot, village_cache, force_not_empty=True)
                time.sleep(0.5)

        if stop_callback():
            return total

        # ---- Phase 4: Build and upgrade in dependency order ----
        print(f"\n{'='*50}")
        print(f"PHASE 4: Build buildings (respecting prerequisites)")
        print(f"{'='*50}")

        # Keep looping until all buildings are built or no progress
        max_rounds = 20  # Prevent infinite loops
        for round_num in range(max_rounds):
            if stop_callback():
                return total

            # Rescan village to get current state
            print(f"\n  --- Round {round_num + 1} ---")
            village_cache = self._scan_village_buildings()
            existing = self._get_existing_names_cached(village_cache)

            built_something = False
            all_built = True

            for building_name, allow_dup in self.AUTO_BUILD_ORDER:
                if stop_callback():
                    return total

                # Skip essential buildings (already handled in Phase 3)
                if building_name in ['Warehouse', 'Granary', 'Cranny', 'Embassy']:
                    continue

                # Skip if already exists (unless duplicates allowed)
                if not allow_dup and self._building_exists(building_name, village_cache):
                    continue

                all_built = False  # There's still something to build

                # Check prerequisites
                prereqs_met, missing = self._check_prerequisites_cached(building_name, village_cache)

                if not prereqs_met:
                    # Check what's missing
                    for prereq_name, req_level, cur_level in missing:
                        if stop_callback():
                            return total

                        prereq_slot = self._find_slot_by_name_cached(prereq_name, village_cache)

                        if not prereq_slot:
                            # Prereq building doesn't exist - build it
                            print(f"  📋 Building {prereq_name} (needed for {building_name})...")
                            empty_slot = self._find_empty_slot_cached(village_cache)
                            if empty_slot:
                                if self._build_new_building(empty_slot, prereq_name):
                                    total += 1
                                    built_something = True
                                    self._update_cache(empty_slot, village_cache, force_not_empty=True)
                            break  # Move to next round after building prereq

                        elif cur_level < req_level:
                            # Prereq exists but needs upgrading
                            print(f"  📋 Upgrading {prereq_name} L{cur_level}->L{req_level} (needed for {building_name})...")
                            if self._try_upgrade(prereq_slot):
                                print(f"     🔧 {prereq_name} L{cur_level} -> L{cur_level+1}")
                                total += 1
                                built_something = True
                            break  # Move to next round after upgrading

                    continue  # Skip this building, prereqs not met

                # Prerequisites are met - build the building
                empty_slot = self._find_empty_slot_cached(village_cache)
                if not empty_slot:
                    print(f"  ✗ No empty slots available")
                    break

                print(f"  🏗️ Building {building_name}...")
                if self._build_new_building(empty_slot, building_name):
                    existing.add(building_name)
                    total += 1
                    built_something = True
                    self._update_cache(empty_slot, village_cache, force_not_empty=True)
                else:
                    print(f"     ✗ Could not build {building_name}")

            # Check if we're done or stuck
            if all_built:
                print(f"\n  ✓ All buildings constructed!")
                break

            if not built_something:
                # Try upgrading resources while waiting for construction
                upgraded = False
                for field_id in range(1, 19):
                    if stop_callback():
                        return total
                    fname, flevel = self._get_field_level(field_id)
                    if flevel < self.target_level and self._try_upgrade(field_id):
                        print(f"  🔨 {fname} L{flevel} -> L{flevel+1} (while waiting)")
                        total += 1
                        upgraded = True
                        break

                if not upgraded:
                    print(f"  ⏳ Waiting for construction to complete...")
                    # Nothing to do, constructions in progress
                    break

        if stop_callback():
            return total

        # ---- Phase 5: Upgrade everything to level 20 ----
        print(f"\n{'='*50}")
        print(f"PHASE 5: Upgrade everything to level 20")
        print(f"{'='*50}")

        # Get list of non-empty building slots from cache (avoid checking empty slots)
        building_slots = [slot_id for slot_id, info in village_cache.items() if not info['is_empty']]
        print(f"  Tracking {len(building_slots)} buildings in village")

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

            # Village buildings - only check slots we know have buildings
            for building_id in building_slots:
                if stop_callback():
                    return total
                name, level = self._get_field_level(building_id)
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
                # No upgrades available - all done or waiting for resources
                break

        return total
