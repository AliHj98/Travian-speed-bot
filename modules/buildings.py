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

    def auto_upgrade_all_to_20(self, session) -> int:
        """
        Continuously upgrade ALL resource fields to level 20.
        Keeps going until all fields are level 20 or no upgrades available.
        """
        print("=" * 50)
        print(f"🚀 AUTO UPGRADE ALL RESOURCES TO LEVEL {self.target_level}")
        print("=" * 50)
        print("Press Ctrl+C to stop\n")

        total_upgrades = 0
        rounds = 0

        try:
            while True:
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                # Check if all fields are at target level
                all_done = True
                fields_status = []

                for field_id in range(1, 19):
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

                if upgraded_this_round == 0:
                    print("No upgrades available, waiting 5s...")
                    time.sleep(5)

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

    def upgrade_to_level(self, building_id: int, target_level: int) -> Dict:
        """
        Upgrade a specific building to a target level.
        Returns dict with results: upgrades performed, final level, success status
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
            print("Press Ctrl+C to stop\n")

            if info['level'] >= target_level:
                result['final_level'] = info['level']
                result['success'] = True
                result['message'] = f"{info['name']} is already at level {info['level']}"
                print(f"✓ {result['message']}")
                return result

            # Upgrade loop
            while True:
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
                    print("  Waiting for upgrade button...")
                    time.sleep(2)
                    continue

                btn_class = upgrade_btn.get_attribute('class') or ''

                if 'disabled' in btn_class:
                    print(f"  L{current_level} - Waiting for resources/queue...")
                    time.sleep(3)
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

    def auto_upgrade_all_buildings(self, session) -> int:
        """
        Continuously upgrade ALL village buildings to max level.
        Keeps going until all buildings are at max level or no upgrades available.
        """
        print("=" * 50)
        print(f"🏗️ AUTO UPGRADE ALL VILLAGE BUILDINGS TO LEVEL {self.target_level}")
        print("=" * 50)
        print("Press Ctrl+C to stop\n")

        total_upgrades = 0
        rounds = 0

        try:
            while True:
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                # Check status of all buildings
                all_done = True
                buildings_status = []

                for building_id in range(19, 41):
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

                if upgraded_this_round == 0:
                    print("No upgrades available, waiting 5s...")
                    time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user")

        print(f"\n{'='*50}")
        print(f"✓ Total building upgrades: {total_upgrades}")
        print(f"{'='*50}")

        return total_upgrades

    # ==================== SMART BUILD ORDER ====================

    # Building GIDs for construction
    BUILDING_GIDS = {
        'Main Building': 15,
        'Barracks': 19,
        'Stable': 20,
        'Workshop': 21,
        'Academy': 22,
        'Smithy': 13,
        'Rally Point': 16,
        'Marketplace': 17,
        'Embassy': 18,
        'Warehouse': 10,
        'Granary': 11,
        'Residence': 25,
        'Palace': 26,
        'Town Hall': 24,
        'Treasury': 27,
        'Trade Office': 28,
        'Cranny': 23,
        'Hero Mansion': 37,
        'Tournament Square': 14,
    }

    # Default order to auto-build in empty slots
    AUTO_BUILD_ORDER = [
        'Warehouse', 'Granary', 'Marketplace', 'Embassy',
        'Academy', 'Smithy', 'Town Hall', 'Stable',
        'Workshop', 'Cranny', 'Hero Mansion', 'Trade Office',
        'Tournament Square', 'Treasury',
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

    def _build_new_building(self, slot_id: int, building_name: str) -> bool:
        """Try to construct a new building in an empty slot."""
        from config import config

        gid = self.BUILDING_GIDS.get(building_name)
        if not gid:
            print(f"  Unknown building: {building_name}")
            return False

        # Navigate to empty slot — should show construction page
        self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
        time.sleep(0.3)

        # Method 1: Direct GID link
        build_links = self.browser.find_elements(By.CSS_SELECTOR,
            f'a[href*="gid={gid}"], .buildingList a[href*="gid={gid}"]')
        if build_links:
            for link in build_links:
                try:
                    if link.is_displayed():
                        link.click()
                        time.sleep(0.3)
                        build_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                        if build_btn:
                            btn_class = build_btn.get_attribute('class') or ''
                            if 'disabled' not in btn_class:
                                build_btn.click()
                                print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                                return True
                            else:
                                print(f"  {building_name}: build button disabled (resources/requirements)")
                                return False
                except:
                    continue

        # Method 2: Navigate through construction categories
        categories = self.browser.find_elements(By.CSS_SELECTOR,
            '.tabContainer .tab, .buildingList .category a, .filterButtons a, nav a')
        for cat in categories:
            try:
                if cat.is_displayed():
                    cat.click()
                    time.sleep(0.3)

                    build_links = self.browser.find_elements(By.CSS_SELECTOR,
                        f'a[href*="gid={gid}"], .buildingList a[href*="gid={gid}"]')
                    if build_links:
                        for link in build_links:
                            try:
                                if link.is_displayed():
                                    link.click()
                                    time.sleep(0.3)
                                    build_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                                    if build_btn:
                                        btn_class = build_btn.get_attribute('class') or ''
                                        if 'disabled' not in btn_class:
                                            build_btn.click()
                                            print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                                            return True
                                        else:
                                            print(f"  {building_name}: build button disabled")
                                            return False
                            except:
                                continue
            except:
                continue

        # Method 3: Search all links for building name
        all_links = self.browser.find_elements(By.CSS_SELECTOR, 'a')
        for link in all_links:
            try:
                text = link.text.strip()
                if building_name.lower() in text.lower():
                    link.click()
                    time.sleep(0.3)
                    build_btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                    if build_btn:
                        btn_class = build_btn.get_attribute('class') or ''
                        if 'disabled' not in btn_class:
                            build_btn.click()
                            print(f"  ✓ Started construction: {building_name} in slot #{slot_id}")
                            return True
            except:
                continue

        print(f"  Could not find {building_name} in construction list")
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
        Smart build order:
        Phase 1: Upgrade all resource fields to level 10
        Phase 2: Upgrade Main Building to level 5
        Phase 3: Upgrade Barracks to level 3
        Phase 4: Auto-fill empty village slots with buildings
        Phase 5: Continue upgrading everything
        Returns total upgrades performed.
        """
        total = 0

        # ---- Phase 1: Resources to level 10 ----
        print(f"\n{'='*50}")
        print(f"PHASE 1: Upgrade all resource fields to level 10")
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
                print(f"  Waiting for queue/resources (5s)...")
                for _ in range(5):
                    if stop_callback():
                        return total
                    time.sleep(1)

        # ---- Phase 2: Main Building to level 5 ----
        if not stop_callback():
            print(f"\n{'='*50}")
            print(f"PHASE 2: Upgrade Main Building to level 5")
            print(f"{'='*50}")

            mb_slot = self._find_building_slot_by_name('Main Building')
            if mb_slot:
                while not stop_callback():
                    name, level = self._get_field_level(mb_slot)
                    if level >= 5:
                        print(f"  ✓ Main Building at level {level}")
                        break
                    if self._try_upgrade(mb_slot):
                        print(f"  🏗️ Main Building L{level} -> L{level+1}")
                        total += 1
                    else:
                        print(f"  Waiting (5s)...")
                        for _ in range(5):
                            if stop_callback():
                                return total
                            time.sleep(1)
            else:
                print(f"  Main Building not found")

        # ---- Phase 3: Barracks to level 3 ----
        if not stop_callback():
            print(f"\n{'='*50}")
            print(f"PHASE 3: Upgrade Barracks to level 3")
            print(f"{'='*50}")

            barracks_slot = self._find_building_slot_by_name('Barracks')
            if barracks_slot:
                while not stop_callback():
                    name, level = self._get_field_level(barracks_slot)
                    if level >= 3:
                        print(f"  ✓ Barracks at level {level}")
                        break
                    if self._try_upgrade(barracks_slot):
                        print(f"  🗡️ Barracks L{level} -> L{level+1}")
                        total += 1
                    else:
                        print(f"  Waiting (5s)...")
                        for _ in range(5):
                            if stop_callback():
                                return total
                            time.sleep(1)
            else:
                print(f"  Barracks not found")

        # ---- Phase 4: Fill empty village slots ----
        if not stop_callback():
            print(f"\n{'='*50}")
            print(f"PHASE 4: Auto-fill empty village slots")
            print(f"{'='*50}")

            existing = self._get_existing_building_names()
            print(f"  Existing buildings: {len(existing)}")

            for building_name in self.AUTO_BUILD_ORDER:
                if stop_callback():
                    return total

                # Allow duplicates for Cranny, Warehouse, Granary
                allow_duplicate = building_name in ['Cranny', 'Warehouse', 'Granary']
                if not allow_duplicate and building_name in existing:
                    continue

                empty_slot = self._find_empty_slot()
                if not empty_slot:
                    print(f"  No more empty slots")
                    break

                print(f"  Building {building_name} in slot #{empty_slot}...")
                if self._build_new_building(empty_slot, building_name):
                    existing.add(building_name)
                    total += 1
                    time.sleep(1)
                else:
                    print(f"  Skipping {building_name} (may need prerequisites)")

        # ---- Phase 5: Continue upgrading everything ----
        if not stop_callback():
            print(f"\n{'='*50}")
            print(f"PHASE 5: Upgrade everything")
            print(f"{'='*50}")

            while not stop_callback():
                all_done = True
                upgraded = False

                # Resources
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
