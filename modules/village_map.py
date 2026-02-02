"""
Village Mapping Module - Scans and caches village building data
"""

import re
import json
import os
import time
from typing import Dict, List, Optional
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from config import config


class VillageMap:
    """Scans and caches village building data for faster operations"""

    CACHE_FILE = 'village_cache.json'

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.villages = {}  # village_name -> building data
        self.current_village = None
        self.load_cache()

    def load_cache(self):
        """Load cached village data from file"""
        try:
            if os.path.exists(self.CACHE_FILE):
                with open(self.CACHE_FILE, 'r') as f:
                    self.villages = json.load(f)
                print(f"✓ Loaded cache for {len(self.villages)} village(s)")
        except:
            self.villages = {}

    def save_cache(self):
        """Save village data to cache file"""
        try:
            with open(self.CACHE_FILE, 'w') as f:
                json.dump(self.villages, f, indent=2)
        except:
            pass

    def get_current_village_name(self) -> str:
        """Get current village name"""
        try:
            elem = self.browser.find_element_fast(By.ID, 'villageNameField')
            if elem:
                return elem.text.strip()
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, '.villageList .active')
            if elem:
                return elem.text.strip()
        except:
            pass
        return "Unknown"

    def scan_village(self, force: bool = False) -> Dict:
        """Scan current village and cache building data"""
        village_name = self.get_current_village_name()
        self.current_village = village_name

        # Check if already cached
        if not force and village_name in self.villages:
            print(f"✓ Using cached data for '{village_name}'")
            return self.villages[village_name]

        print(f"\n🔍 Scanning village: {village_name}")
        print("=" * 40)

        village_data = {
            'name': village_name,
            'scanned_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'resource_fields': {},  # slot 1-18
            'buildings': {},  # slot 19-40
            'building_types': {}  # gid -> slot mapping
        }

        # Scan resource fields (1-18)
        print("Scanning resource fields (1-18)...")
        for slot_id in range(1, 19):
            info = self._scan_slot(slot_id)
            if info:
                village_data['resource_fields'][slot_id] = info
                print(f"  #{slot_id}: {info['name']} L{info['level']}")

        # Scan village buildings (19-40)
        print("\nScanning village buildings (19-40)...")
        for slot_id in range(19, 41):
            info = self._scan_slot(slot_id)
            if info and info['name'] != 'Unknown' and info['name'] != 'Empty':
                village_data['buildings'][slot_id] = info
                # Map building type (gid) to slot
                if info.get('gid'):
                    village_data['building_types'][info['gid']] = slot_id
                print(f"  #{slot_id}: {info['name']} L{info['level']}")

        # Cache it
        self.villages[village_name] = village_data
        self.save_cache()

        print(f"\n✓ Village scan complete!")
        print(f"  Resource fields: {len(village_data['resource_fields'])}")
        print(f"  Buildings: {len(village_data['buildings'])}")

        return village_data

    def _scan_slot(self, slot_id: int) -> Optional[Dict]:
        """Scan a single building slot"""
        try:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")

            info = {
                'slot': slot_id,
                'name': 'Unknown',
                'level': 0,
                'gid': None
            }

            # Get building name and level from h1
            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1:
                text = h1.text
                if 'Level' in text:
                    info['name'] = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        info['level'] = int(match.group(1))
                elif text.strip():
                    info['name'] = text.strip()

            # Try to get gid from URL or page
            url = self.browser.current_url
            gid_match = re.search(r'gid=(\d+)', url)
            if gid_match:
                info['gid'] = int(gid_match.group(1))

            # Check if empty slot
            if 'construct' in url.lower() or info['name'] == 'Unknown':
                info['name'] = 'Empty'
                info['level'] = 0

            return info

        except:
            return None

    def get_building_slot(self, building_name: str) -> Optional[int]:
        """Get slot ID for a building by name (uses cache)"""
        if not self.current_village or self.current_village not in self.villages:
            self.scan_village()

        village = self.villages.get(self.current_village, {})
        name_lower = building_name.lower()

        # Check village buildings
        for slot_id, info in village.get('buildings', {}).items():
            if name_lower in info['name'].lower():
                return int(slot_id)

        # Check resource fields
        for slot_id, info in village.get('resource_fields', {}).items():
            if name_lower in info['name'].lower():
                return int(slot_id)

        return None

    def get_building_by_gid(self, gid: int) -> Optional[int]:
        """Get slot ID for a building by type (gid)"""
        if not self.current_village or self.current_village not in self.villages:
            self.scan_village()

        village = self.villages.get(self.current_village, {})
        return village.get('building_types', {}).get(str(gid))

    def get_resource_fields(self) -> Dict:
        """Get all resource fields (uses cache)"""
        if not self.current_village or self.current_village not in self.villages:
            self.scan_village()

        village = self.villages.get(self.current_village, {})
        return village.get('resource_fields', {})

    def get_buildings(self) -> Dict:
        """Get all village buildings (uses cache)"""
        if not self.current_village or self.current_village not in self.villages:
            self.scan_village()

        village = self.villages.get(self.current_village, {})
        return village.get('buildings', {})

    def get_fields_by_type(self, field_type: str) -> List[Dict]:
        """Get all fields of a specific type (e.g., 'Cropland', 'Clay Pit')"""
        fields = []
        type_lower = field_type.lower()

        for slot_id, info in self.get_resource_fields().items():
            if type_lower in info['name'].lower():
                fields.append({'slot': int(slot_id), **info})

        return fields

    def get_lowest_level_field(self, field_type: str = None) -> Optional[Dict]:
        """Get the field with lowest level (optionally filtered by type)"""
        fields = self.get_resource_fields()
        lowest = None

        for slot_id, info in fields.items():
            if field_type and field_type.lower() not in info['name'].lower():
                continue
            if lowest is None or info['level'] < lowest['level']:
                lowest = {'slot': int(slot_id), **info}

        return lowest

    def clear_cache(self, village_name: str = None):
        """Clear cache for a village or all villages"""
        if village_name:
            if village_name in self.villages:
                del self.villages[village_name]
        else:
            self.villages = {}
        self.save_cache()
        print("✓ Cache cleared")

    def print_summary(self):
        """Print village summary"""
        if not self.current_village or self.current_village not in self.villages:
            print("No village data. Run scan first.")
            return

        village = self.villages[self.current_village]
        print(f"\n{'='*50}")
        print(f"Village: {village['name']}")
        print(f"Scanned: {village.get('scanned_at', 'Unknown')}")
        print(f"{'='*50}")

        print("\nResource Fields:")
        for slot_id, info in sorted(village.get('resource_fields', {}).items(), key=lambda x: int(x[0])):
            print(f"  #{slot_id:2}: {info['name']:<15} L{info['level']}")

        print("\nBuildings:")
        for slot_id, info in sorted(village.get('buildings', {}).items(), key=lambda x: int(x[0])):
            print(f"  #{slot_id:2}: {info['name']:<20} L{info['level']}")
