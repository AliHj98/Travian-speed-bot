"""
Farm Finder Module - Automatic scanning and farm discovery
"""

import math
import re
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from modules.farming import FarmListManager
from config import config


@dataclass
class ScanFilter:
    """Filter criteria for farm scanning"""
    radius: int = 10
    max_population: int = 50
    include_natars: bool = True
    include_player_villages: bool = True
    include_unoccupied_oases: bool = True
    include_occupied_oases: bool = True
    exclude_alliances: List[str] = field(default_factory=list)
    exclude_players: List[str] = field(default_factory=list)


@dataclass
class ScannedTile:
    """Parsed information from a map tile"""
    x: int
    y: int
    tile_type: str  # 'village', 'oasis_unoccupied', 'oasis_occupied', 'wilderness', 'empty'
    name: str = ""
    player_name: str = ""
    alliance: str = ""
    population: int = 0
    distance: float = 0.0
    is_capital: bool = False
    tribe: str = ""


class FarmFinder:
    """Scans the map and auto-adds viable farm targets to farm lists"""

    def __init__(self, browser: BrowserManager, farming: FarmListManager):
        self.browser = browser
        self.farming = farming

    def scan_area(self, center_x: int, center_y: int, scan_filter: ScanFilter,
                  target_list: str, stop_callback: Callable = None) -> Dict:
        """Main scanning loop - scan coordinates in a radius, parse tiles, add matches.

        Returns stats dict with found/added/skipped/scanned counts.
        """
        stats = {
            'scanned': 0,
            'found': 0,
            'added': 0,
            'skipped_duplicate': 0,
            'skipped_filter': 0,
            'errors': 0,
        }

        coords = self._generate_spiral_coords(center_x, center_y, scan_filter.radius)
        total = len(coords)

        print(f"\n  Scanning {total} tiles around ({center_x}|{center_y}) radius {scan_filter.radius}")
        print(f"  Target list: {target_list}")
        print(f"  Max population: {scan_filter.max_population}")
        print(f"  Press Q/S to stop\n")

        for i, (x, y) in enumerate(coords):
            if stop_callback and stop_callback():
                print(f"\n  Scan interrupted at tile {i}/{total}")
                break

            # Skip coordinates already in any farm list
            existing_list = self.farming.is_coordinate_in_any_list(x, y)
            if existing_list:
                stats['skipped_duplicate'] += 1
                continue

            # Skip already scanned coords (from scan_history)
            coord_key = f"{x},{y}"
            if coord_key in self.farming.scan_history.get('scanned_coords', []):
                stats['skipped_duplicate'] += 1
                continue

            # Parse tile
            tile = self._parse_tile(x, y)
            stats['scanned'] += 1

            if tile is None:
                stats['errors'] += 1
                continue

            # Record in scan history
            scanned = self.farming.scan_history.setdefault('scanned_coords', [])
            scanned.append(coord_key)

            # Apply filters
            if tile.tile_type == 'empty' or tile.tile_type == 'wilderness':
                continue

            if not self._matches_filter(tile, scan_filter):
                stats['skipped_filter'] += 1
                continue

            stats['found'] += 1

            # Auto-add to target list
            farm_id = self.farming.add_farm_to_list(
                list_name=target_list,
                name=tile.name or f"({x}|{y})",
                x=x,
                y=y,
                notes=f"pop:{tile.population} type:{tile.tile_type} player:{tile.player_name}",
            )

            if farm_id > 0:
                stats['added'] += 1

            # Progress display
            pct = int((i + 1) / total * 100)
            print(f"  [{i+1}/{total}] ({pct}%) Scanning ({x}|{y}) | "
                  f"Found: {stats['found']} | Added: {stats['added']}")

        # Save scan history
        self.farming.save_farms()

        # Print summary
        print(f"\n  {'='*50}")
        print(f"  Scan complete!")
        print(f"  Tiles scanned: {stats['scanned']}")
        print(f"  Matches found: {stats['found']}")
        print(f"  Farms added: {stats['added']}")
        print(f"  Skipped (duplicate): {stats['skipped_duplicate']}")
        print(f"  Skipped (filter): {stats['skipped_filter']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  {'='*50}")

        return stats

    def _parse_tile(self, x: int, y: int) -> Optional[ScannedTile]:
        """Navigate to position_details.php and extract tile information"""
        try:
            self.browser.navigate_to(f"{config.base_url}/position_details.php?x={x}&y={y}")
            time.sleep(0.3)

            tile = ScannedTile(x=x, y=y, tile_type='empty')
            tile.distance = math.sqrt(
                (x - self.farming.home_x) ** 2 + (y - self.farming.home_y) ** 2
            )

            # Get tile details container
            details = self.browser.find_element_fast(By.CSS_SELECTOR, '#tileDetails')
            if not details:
                return tile

            page_text = details.text if details else ""
            page_text_lower = page_text.lower()

            # Parse title/name
            title_elem = None
            for sel in ['#tileDetails h1', '.villNameAndOffs h1', '#tileDetails .name',
                        '.detailImage h1', 'h1.titleInHeader']:
                title_elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if title_elem and title_elem.text.strip():
                    break

            if title_elem:
                tile.name = title_elem.text.strip()

            # Determine tile type
            if 'oasis' in page_text_lower:
                # Check if oasis is occupied (has troops/player)
                has_troops = bool(self.browser.find_element_fast(By.CSS_SELECTOR, '#tileDetails table.troop_details'))
                has_owner = False
                for sel in ['.playerName', 'a[href*="profile"]']:
                    elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                    if elem and elem.text.strip():
                        has_owner = True
                        break

                if has_owner or has_troops:
                    tile.tile_type = 'oasis_occupied'
                    tile.name = tile.name or f"Occupied Oasis ({x}|{y})"
                else:
                    tile.tile_type = 'oasis_unoccupied'
                    tile.name = tile.name or f"Unoccupied Oasis ({x}|{y})"
            elif self._has_village_indicators(page_text_lower):
                tile.tile_type = 'village'
                tile.name = tile.name or f"Village ({x}|{y})"
            else:
                tile.tile_type = 'wilderness'
                return tile

            # Parse player name
            for sel in ['.playerName', '#tileDetails a[href*="profile"]',
                        'a[href*="spieler.php"]']:
                player_elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if player_elem and player_elem.text.strip():
                    tile.player_name = player_elem.text.strip()
                    break

            # Parse alliance
            for sel in ['.allianceName', '#tileDetails a[href*="allianz"]',
                        'a[href*="alliance"]']:
                alliance_elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if alliance_elem and alliance_elem.text.strip():
                    tile.alliance = alliance_elem.text.strip()
                    break

            # Parse population
            tile.population = self._parse_population(details)

            # Check for capital
            if 'capital' in page_text_lower or '(capital)' in tile.name.lower():
                tile.is_capital = True

            # Check for Natars
            if 'natar' in tile.player_name.lower() or 'natar' in page_text_lower:
                tile.player_name = tile.player_name or 'Natars'

            return tile

        except Exception as e:
            return None

    def _has_village_indicators(self, text: str) -> bool:
        """Check if page text indicates a village"""
        indicators = ['population', 'inhabitants', 'einwohner', 'tribe',
                      'player', 'alliance', 'capital']
        return any(ind in text for ind in indicators)

    def _parse_population(self, details_elem) -> int:
        """Extract population number from the tile details"""
        try:
            # Try direct selectors
            for sel in ['.population', 'td.inhabitants', '.inhabitants']:
                pop_elem = details_elem.find_element(By.CSS_SELECTOR, sel)
                if pop_elem:
                    text = pop_elem.text.strip()
                    match = re.search(r'(\d+)', text)
                    if match:
                        return int(match.group(1))
        except:
            pass

        try:
            # Fallback: find table rows with "Population" or "Inhabitants" label
            rows = details_elem.find_elements(By.CSS_SELECTOR, 'table tr')
            for row in rows:
                text = row.text.lower()
                if 'population' in text or 'inhabitants' in text or 'einwohner' in text:
                    match = re.search(r'(\d+)', row.text)
                    if match:
                        return int(match.group(1))
        except:
            pass

        try:
            # Last fallback: regex on full text
            full_text = details_elem.text
            match = re.search(r'(?:population|inhabitants|einwohner)[:\s]*(\d+)', full_text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        except:
            pass

        return 0

    def _matches_filter(self, tile: ScannedTile, scan_filter: ScanFilter) -> bool:
        """Check if a tile matches the scan filter criteria"""
        # Filter by tile type
        if tile.tile_type == 'oasis_unoccupied' and not scan_filter.include_unoccupied_oases:
            return False
        if tile.tile_type == 'oasis_occupied' and not scan_filter.include_occupied_oases:
            return False
        if tile.tile_type == 'village' and not scan_filter.include_player_villages:
            return False

        # Filter Natars
        if 'natar' in tile.player_name.lower() and not scan_filter.include_natars:
            return False

        # Filter by population (0 means unknown - allow it)
        if tile.population > 0 and tile.population > scan_filter.max_population:
            return False

        # Filter by excluded alliances
        if tile.alliance and scan_filter.exclude_alliances:
            for excluded in scan_filter.exclude_alliances:
                if excluded.lower() in tile.alliance.lower():
                    return False

        # Filter by excluded players
        if tile.player_name and scan_filter.exclude_players:
            for excluded in scan_filter.exclude_players:
                if excluded.lower() in tile.player_name.lower():
                    return False

        return True

    def _generate_spiral_coords(self, center_x: int, center_y: int, radius: int) -> List[tuple]:
        """Generate coordinates in a spiral pattern outward from center (closest first)"""
        coords = []
        for r in range(1, radius + 1):
            # Top edge: (center_x - r to center_x + r, center_y + r)
            for dx in range(-r, r + 1):
                coords.append((center_x + dx, center_y + r))
            # Right edge (excluding corner): (center_x + r, center_y + r-1 down to center_y - r)
            for dy in range(r - 1, -r - 1, -1):
                coords.append((center_x + r, center_y + dy))
            # Bottom edge (excluding corner): (center_x + r-1 to center_x - r, center_y - r)
            for dx in range(r - 1, -r - 1, -1):
                coords.append((center_x + dx, center_y - r))
            # Left edge (excluding corners): (center_x - r, center_y - r+1 to center_y + r-1)
            for dy in range(-r + 1, r):
                coords.append((center_x - r, center_y + dy))

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for c in coords:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def clear_scan_history(self):
        """Clear the scan history so tiles can be re-scanned"""
        count = len(self.farming.scan_history.get('scanned_coords', []))
        self.farming.scan_history = {'scanned_coords': []}
        self.farming.save_farms()
        print(f"✓ Cleared {count} entries from scan history")

    def estimate_scan_time(self, radius: int) -> tuple:
        """Estimate scan time and tile count for a given radius.
        Returns (tile_count, estimated_seconds)."""
        # Spiral covers all tiles in the radius
        tile_count = 0
        for r in range(1, radius + 1):
            tile_count += 8 * r  # perimeter of each ring
        # ~0.5s per tile (page load + parse)
        estimated_seconds = int(tile_count * 0.5)
        return tile_count, estimated_seconds
