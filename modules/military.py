import re
import time
import base64
import os
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from modules.resources import ResourceMonitor
from config import config

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


@dataclass
class VillageTrainingConfig:
    """Training configuration for a single village"""
    village_id: str
    village_name: str
    enabled: bool = True
    barracks_troop: str = ""  # Input name like 't1'
    barracks_troop_name: str = ""  # Display name like 'Legionnaire'
    stable_troop: str = ""
    stable_troop_name: str = ""
    train_barracks: bool = True
    train_stable: bool = False


class MilitaryManager:
    """Manages military units, training, and attacks"""

    # Building GIDs (type IDs)
    BARRACKS_GID = 19
    STABLE_GID = 20
    WORKSHOP_GID = 21
    RALLY_POINT_GID = 16
    SMITHY_GID = 13
    ACADEMY_GID = 22
    TOWN_HALL_GID = 24

    def __init__(self, browser: BrowserManager, resource_monitor: ResourceMonitor):
        self.browser = browser
        self.resources = resource_monitor
        self.troops = {}
        self.building_cache = {}  # gid -> slot_id mapping
        self.screenshots_dir = 'screenshots'
        os.makedirs(self.screenshots_dir, exist_ok=True)

        # Initialize Claude client for vision
        self.client = None
        if ANTHROPIC_AVAILABLE and config.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def find_building_slot(self, gid: int) -> Optional[int]:
        """Find the slot ID for a building type in the village (uses cache)"""
        # Check local cache first
        if gid in self.building_cache:
            return self.building_cache[gid]

        # Try to use village map if available
        try:
            from modules.village_map import VillageMap
            if not hasattr(self, 'village_map'):
                self.village_map = VillageMap(self.browser)

            slot = self.village_map.get_building_by_gid(gid)
            if slot:
                self.building_cache[gid] = slot
                return slot
        except:
            pass

        # Fallback: scan manually
        from config import config
        gid_to_name = {
            self.BARRACKS_GID: 'barracks',
            self.STABLE_GID: 'stable',
            self.WORKSHOP_GID: 'workshop',
            self.RALLY_POINT_GID: 'rally',
            self.SMITHY_GID: 'smithy',
            self.ACADEMY_GID: 'academy',
            self.TOWN_HALL_GID: 'townhall',
        }
        target_name = gid_to_name.get(gid, '')

        for slot_id in range(19, 41):
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot_id}")
            url = self.browser.current_url

            if f"gid={gid}" in url:
                self.building_cache[gid] = slot_id
                return slot_id

            h1 = self.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            if h1 and target_name in h1.text.lower():
                self.building_cache[gid] = slot_id
                return slot_id

        return None

    def navigate_to_barracks(self) -> bool:
        """Navigate to barracks"""
        from config import config

        slot = self.find_building_slot(self.BARRACKS_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Barracks not found in village")
        return False

    def navigate_to_stable(self) -> bool:
        """Navigate to stable"""
        from config import config

        slot = self.find_building_slot(self.STABLE_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Stable not found in village")
        return False

    def navigate_to_rally_point(self) -> bool:
        """Navigate to rally point"""
        from config import config

        slot = self.find_building_slot(self.RALLY_POINT_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Rally Point not found in village")
        return False

    def get_available_troops_to_train(self) -> List[Dict]:
        """Get list of troops available to train on current page"""
        troops = []

        # Find ALL input fields on the page that look like troop inputs
        # Travian typically uses inputs named t1, t2, t3, etc.
        all_inputs = self.browser.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[type="number"]')

        print(f"  Found {len(all_inputs)} input fields on page")

        for inp in all_inputs:
            try:
                input_name = inp.get_attribute('name')
                if not input_name:
                    continue

                # Skip non-troop inputs
                if input_name in ['name', 'user', 'username', 'password', 'pass', 'x', 'y']:
                    continue

                # Check if it's visible
                if not inp.is_displayed():
                    continue

                # Try to find associated label/name
                name = f"Troop ({input_name})"

                # Try to find parent row and get troop name
                try:
                    parent = inp.find_element(By.XPATH, './ancestor::tr')
                    if parent:
                        text = parent.text
                        # First word is usually the troop name
                        words = text.split()
                        if words:
                            name = words[0]
                except:
                    pass

                # Try to find max trainable
                max_trainable = 0
                try:
                    # Look for nearby link with number (max button)
                    parent = inp.find_element(By.XPATH, './..')
                    links = parent.find_elements(By.CSS_SELECTOR, 'a')
                    for link in links:
                        text = link.text
                        match = re.search(r'(\d+)', text)
                        if match:
                            max_trainable = int(match.group(1))
                            break
                except:
                    pass

                troops.append({
                    'name': name,
                    'input_name': input_name,
                    'max': max_trainable,
                    'input_element': inp
                })

                print(f"    Found: {name} (input: {input_name}, max: {max_trainable})")

            except Exception as e:
                continue

        return troops

    def train_troops_by_input(self, input_name: str, amount: int) -> bool:
        """Train troops using the input field name"""
        try:
            # Find the input
            input_elem = self.browser.find_element(By.NAME, input_name, timeout=2)
            if not input_elem:
                print(f"  Input field '{input_name}' not found")
                return False

            # Clear and enter amount
            input_elem.clear()
            input_elem.send_keys(str(amount))

            # Find and click train/submit button
            train_btn = self.browser.find_element(
                By.CSS_SELECTOR,
                'button[type="submit"], input[type="submit"], button.green, .startTraining button',
                timeout=2
            )

            if train_btn:
                train_btn.click()
                time.sleep(0.5)
                return True

            return False

        except Exception as e:
            print(f"  Error: {e}")
            return False

    def train_troops(self, troop_name: str, amount: int, building: str = 'barracks') -> bool:
        """Train specified amount of troops by name"""
        print(f"\n⚔️  Training {amount}x {troop_name}")

        # Navigate to correct building
        if building == 'barracks':
            if not self.navigate_to_barracks():
                return False
        elif building == 'stable':
            if not self.navigate_to_stable():
                return False

        # Get available troops
        available = self.get_available_troops_to_train()

        if not available:
            print("  No troops available to train")
            return False

        # Find matching troop
        troop_name_lower = troop_name.lower()
        for troop in available:
            if troop_name_lower in troop['name'].lower():
                # Train this troop
                actual_amount = min(amount, troop['max']) if troop['max'] > 0 else amount

                if self.train_troops_by_input(troop['input_name'], actual_amount):
                    print(f"  ✓ Queued {actual_amount}x {troop['name']}")
                    return True
                else:
                    print(f"  ✗ Failed to train {troop['name']}")
                    return False

        print(f"  Troop '{troop_name}' not found. Available:")
        for t in available:
            print(f"    - {t['name']} (max: {t['max']})")

        return False

    def auto_train_troops(self, building: str = 'barracks', fill_queue: bool = True) -> bool:
        """Automatically train troops - fills the training queue"""
        print(f"\n⚔️  Auto-training in {building}...")

        # Navigate to building
        if building == 'barracks':
            if not self.navigate_to_barracks():
                return False
        elif building == 'stable':
            if not self.navigate_to_stable():
                return False

        # Get available troops
        available = self.get_available_troops_to_train()

        if not available:
            print("  No troops available to train")
            return False

        print(f"  Found {len(available)} troop types")

        trained_any = False

        for troop in available:
            if troop['max'] > 0:
                # Train maximum available
                amount = troop['max'] if fill_queue else min(10, troop['max'])

                print(f"  Training {amount}x {troop['name']}...")

                if troop['input_element']:
                    try:
                        troop['input_element'].clear()
                        troop['input_element'].send_keys(str(amount))
                        trained_any = True
                    except:
                        pass

        if trained_any:
            # Click train button
            train_btn = self.browser.find_element(
                By.CSS_SELECTOR,
                'button[type="submit"], input[type="submit"], button.green',
                timeout=2
            )
            if train_btn:
                train_btn.click()
                time.sleep(0.5)
                print("  ✓ Training queued!")
                return True

        print("  No troops could be trained (insufficient resources or queue full)")
        return False

    def get_troop_counts(self) -> Dict[str, int]:
        """Get current troop counts in the village"""
        troops = {}

        try:
            if not self.navigate_to_rally_point():
                return {}

            # Look for troops table
            troop_cells = self.browser.find_elements(By.CSS_SELECTOR, '.troop_details td, .troops td')

            for i in range(0, len(troop_cells), 2):
                try:
                    name = troop_cells[i].text.strip()
                    count_text = troop_cells[i + 1].text.strip()
                    count = int(re.sub(r'[^\d]', '', count_text) or 0)
                    if name:
                        troops[name] = count
                except:
                    continue

            self.troops = troops

        except Exception as e:
            print(f"  Error getting troops: {e}")

        return troops

    def send_attack(self, target_x: int, target_y: int, troops: Dict[str, int] = None, attack_type: str = 'attack') -> bool:
        """Send an attack to coordinates"""
        print(f"\n⚔️  Sending {attack_type} to ({target_x}, {target_y})")

        try:
            if not self.navigate_to_rally_point():
                return False

            # Click on send troops tab/link
            send_link = self.browser.find_element(
                By.CSS_SELECTOR,
                'a[href*="tt=2"], .tab.sendTroops, a:contains("Send")',
                timeout=2
            )
            if send_link:
                send_link.click()
                time.sleep(0.5)

            # Enter coordinates
            x_input = self.browser.find_element(By.CSS_SELECTOR, 'input[name="x"], input#xCoordInput', timeout=2)
            y_input = self.browser.find_element(By.CSS_SELECTOR, 'input[name="y"], input#yCoordInput', timeout=2)

            if x_input and y_input:
                x_input.clear()
                x_input.send_keys(str(target_x))
                y_input.clear()
                y_input.send_keys(str(target_y))
            else:
                print("  Could not find coordinate inputs")
                return False

            # Enter troop amounts if specified
            if troops:
                for troop_name, amount in troops.items():
                    # Find input for this troop type
                    inputs = self.browser.find_elements(By.CSS_SELECTOR, 'input[name^="t"]')
                    for inp in inputs:
                        # Match by nearby label or position
                        try:
                            parent = inp.find_element(By.XPATH, '..')
                            if troop_name.lower() in parent.text.lower():
                                inp.clear()
                                inp.send_keys(str(amount))
                                break
                        except:
                            continue

            # Select attack type
            # 2 = Reinforcement, 3 = Normal Attack, 4 = Raid
            type_value = '4' if attack_type == 'raid' else '3'
            attack_radio = self.browser.find_element(By.CSS_SELECTOR, f'input[value="{type_value}"]', timeout=2)
            if attack_radio:
                attack_radio.click()

            # Click send/confirm
            submit_btn = self.browser.find_element(
                By.CSS_SELECTOR,
                'button[type="submit"], input[type="submit"]',
                timeout=2
            )
            if submit_btn:
                submit_btn.click()
                time.sleep(1)

                # Confirm on second page if needed
                confirm_btn = self.browser.find_element(
                    By.CSS_SELECTOR,
                    'button[type="submit"], input[type="submit"]',
                    timeout=2
                )
                if confirm_btn:
                    confirm_btn.click()
                    print(f"  ✓ {attack_type.capitalize()} sent!")
                    return True

        except Exception as e:
            print(f"  Error: {e}")

        return False

    def send_raid(self, target_x: int, target_y: int, troops: Dict[str, int] = None) -> bool:
        """Send a raid (farming) attack"""
        return self.send_attack(target_x, target_y, troops, attack_type='raid')

    def check_incoming_attacks(self) -> List[Dict]:
        """Check for incoming attacks"""
        incoming = []

        try:
            # Check for attack indicator in the UI
            attack_indicators = self.browser.find_elements(
                By.CSS_SELECTOR,
                '.attack, .movement.attack, #movements .attack, .incoming'
            )

            for elem in attack_indicators:
                try:
                    text = elem.text
                    incoming.append({
                        'type': 'attack',
                        'info': text,
                        'attacker': 'Unknown',
                        'arrival_time': 'Unknown'
                    })
                except:
                    pass

            if incoming:
                print(f"⚠️  {len(incoming)} incoming attack(s)!")

        except Exception as e:
            print(f"  Error checking attacks: {e}")

        return incoming

    def get_training_queue(self) -> List[Dict]:
        """Get current training queue"""
        queue = []

        try:
            # Look for queue elements
            queue_items = self.browser.find_elements(
                By.CSS_SELECTOR,
                '.trainQueue li, .buildingQueue li, .queueEntry'
            )

            for item in queue_items:
                try:
                    text = item.text
                    queue.append({
                        'info': text,
                        'troop_type': 'Unknown',
                        'amount': 0
                    })
                except:
                    pass

        except Exception as e:
            print(f"  Error getting queue: {e}")

        return queue

    def train_max_troops(self, building: str = 'barracks') -> int:
        """Train maximum troops of all types available"""
        print(f"\n⚔️  Training MAX troops in {building}...")

        if building == 'barracks':
            if not self.navigate_to_barracks():
                return 0
        elif building == 'stable':
            if not self.navigate_to_stable():
                return 0

        total_trained = 0

        # Method 1: Try to find and click "train max" links first
        max_links = self.browser.find_elements(By.CSS_SELECTOR, 'a[onclick*="max"], a.max, .cmark1 a')
        if max_links:
            print(f"  Found {len(max_links)} max links, clicking them...")
            for link in max_links:
                try:
                    if link.is_displayed():
                        link.click()
                        time.sleep(0.1)
                except:
                    pass

        # Method 2: Get available troops and fill inputs
        available = self.get_available_troops_to_train()

        if not available:
            print("  No troop inputs found, trying Claude Vision...")
            return self.train_with_claude_vision()

        for troop in available:
            if troop['input_element']:
                try:
                    # If we have max value, use it; otherwise try a large number
                    amount = troop['max'] if troop['max'] > 0 else 99999999

                    troop['input_element'].clear()
                    troop['input_element'].send_keys(str(amount))

                    if troop['max'] > 0:
                        total_trained += troop['max']
                        print(f"  {troop['name']}: {troop['max']}")
                    else:
                        print(f"  {troop['name']}: MAX")
                except:
                    pass

        # Click train button
        train_btn = self.browser.find_element(
            By.CSS_SELECTOR,
            'button[type="submit"], input[type="submit"], button.green, .green.startTraining',
            timeout=2
        )
        if train_btn:
            try:
                train_btn.click()
                print(f"  ✓ Training submitted!")
                time.sleep(0.5)
            except Exception as e:
                print(f"  ✗ Could not click train button: {e}")

        return total_trained

    def train_with_claude_vision(self) -> int:
        """Use Claude Vision to analyze the page and train troops"""
        if not self.client:
            print("  Claude Vision not available")
            return 0

        print("  Using Claude Vision to analyze training page...")

        # Take screenshot
        screenshot_path = os.path.join(self.screenshots_dir, 'barracks.png')
        self.browser.driver.save_screenshot(screenshot_path)

        try:
            with open(screenshot_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Ask Claude to analyze the page
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": "This is a Travian barracks/training page. Look for input fields where I can enter the number of troops to train. Tell me the CSS selector or XPath to find: 1) The input fields for troop amounts 2) The train/submit button. Reply in this format:\nINPUTS: <selector>\nBUTTON: <selector>\nIf you see specific input names like t1, t2, etc, list them."
                            }
                        ],
                    }
                ],
            )

            response = message.content[0].text
            print(f"  Claude analysis: {response[:200]}...")

            # Try to extract selectors from response
            # Look for common patterns Claude might suggest
            input_patterns = ['input[name^="t"]', 'input.troop', '.troopInput', 'input[type="text"]']
            button_patterns = ['button.green', 'button[type="submit"]', '.startTraining', 'input[type="submit"]']

            # Try each pattern
            for pattern in input_patterns:
                inputs = self.browser.find_elements(By.CSS_SELECTOR, pattern)
                if inputs:
                    print(f"  Found {len(inputs)} inputs with pattern: {pattern}")
                    for inp in inputs:
                        try:
                            if inp.is_displayed():
                                inp.clear()
                                inp.send_keys("99999999")
                        except:
                            pass
                    break

            for pattern in button_patterns:
                btn = self.browser.find_element(By.CSS_SELECTOR, pattern, timeout=1)
                if btn:
                    try:
                        btn.click()
                        print(f"  ✓ Clicked train button with pattern: {pattern}")
                        return 1
                    except:
                        pass

        except Exception as e:
            print(f"  Claude Vision error: {e}")

        return 0

    def debug_training_page(self):
        """Debug method to show what's on the current training page"""
        print("\n=== DEBUG: Training Page Analysis ===")

        # Get page title
        h1 = self.browser.find_element(By.CSS_SELECTOR, 'h1, .titleInHeader', timeout=2)
        if h1:
            print(f"Page title: {h1.text}")

        # Find all inputs
        all_inputs = self.browser.find_elements(By.CSS_SELECTOR, 'input')
        print(f"\nAll inputs ({len(all_inputs)}):")
        for inp in all_inputs:
            try:
                name = inp.get_attribute('name')
                inp_type = inp.get_attribute('type')
                visible = inp.is_displayed()
                print(f"  - name='{name}' type='{inp_type}' visible={visible}")
            except:
                pass

        # Find all buttons
        all_buttons = self.browser.find_elements(By.CSS_SELECTOR, 'button, input[type="submit"]')
        print(f"\nAll buttons ({len(all_buttons)}):")
        for btn in all_buttons:
            try:
                text = btn.text or btn.get_attribute('value')
                btn_class = btn.get_attribute('class')
                print(f"  - text='{text}' class='{btn_class}'")
            except:
                pass

        # Find all links with numbers (max links)
        all_links = self.browser.find_elements(By.CSS_SELECTOR, 'a')
        max_links = []
        for link in all_links:
            try:
                text = link.text
                if re.search(r'\d+', text):
                    max_links.append(text)
            except:
                pass
        print(f"\nLinks with numbers: {max_links[:10]}")

        print("=== END DEBUG ===\n")

    def train_single_troop(self, troop: Dict, amount: int) -> bool:
        """Train a single troop type with specified amount"""
        try:
            if troop['input_element']:
                troop['input_element'].clear()
                troop['input_element'].send_keys(str(amount))

                # Click submit button immediately
                btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button[type="submit"]')
                if not btn:
                    btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'button.green')
                if not btn:
                    btn = self.browser.find_element_fast(By.CSS_SELECTOR, 'input[type="submit"]')

                if btn:
                    btn.click()
                    print(f"  ✓ Training {amount}x {troop['name']}!")
                    return True
                else:
                    print("  ✗ Could not find submit button")
            else:
                print("  ✗ No input element for this troop")

        except Exception as e:
            print(f"  ✗ Error: {e}")

        return False

    def train_simple(self, amount: int = 99999999) -> bool:
        """Simple training - just fill all visible inputs and click submit"""
        print(f"\n⚔️  Simple training mode...")

        # Find all text/number inputs
        inputs = self.browser.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[type="number"]')

        filled = 0
        for inp in inputs:
            try:
                name = inp.get_attribute('name') or ''
                # Skip non-troop inputs
                if any(x in name.lower() for x in ['name', 'user', 'pass', 'search', 'coord']):
                    continue
                if inp.is_displayed():
                    inp.clear()
                    inp.send_keys(str(amount))
                    filled += 1
            except:
                pass

        print(f"  Filled {filled} input fields")

        if filled > 0:
            # Click submit
            btn = self.browser.find_element(
                By.CSS_SELECTOR,
                'button[type="submit"], input[type="submit"], button.green, .green',
                timeout=2
            )
            if btn:
                btn.click()
                print("  ✓ Clicked submit!")
                return True

        return False

    def auto_train_continuous(self, buildings: List[str] = None, interval: int = 30) -> int:
        """
        Continuously train troops until stopped.
        Returns total troops trained.
        """
        if buildings is None:
            buildings = ['barracks']

        print("=" * 50)
        print(f"🔄 AUTO TRAIN TROOPS")
        print(f"Buildings: {', '.join(buildings)}")
        print(f"Interval: {interval}s")
        print("=" * 50)
        print("Press Ctrl+C to stop\n")

        total_trained = 0
        rounds = 0

        try:
            while True:
                rounds += 1
                print(f"\n--- Round {rounds} ---")

                for building in buildings:
                    count = self.train_max_troops(building)
                    total_trained += count

                if total_trained == 0:
                    print(f"Waiting {interval}s...")

                time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user")

        print(f"\n{'='*50}")
        print(f"✓ Total troops trained: {total_trained}")
        print(f"{'='*50}")

        return total_trained

    # ==================== MULTI-VILLAGE TRAINING ====================

    VILLAGE_CONFIG_FILE = 'village_training.json'

    def get_all_villages(self) -> List[Dict]:
        """Get list of all villages owned by the player"""
        from config import config

        villages = []

        try:
            # Make sure we're on a page that shows the village list
            self.browser.navigate_to(f"{config.base_url}/dorf1.php")
            time.sleep(0.5)

            # Method 1: Sidebar village list — look for clickable village entries
            # Try multiple selectors used by different Travian versions
            selectors = [
                '#sidebarBoxVillagelist .villageList li a',
                '#sidebarBoxVillagelist a',
                '.villageList a',
                '.village a',
                '#villageListLinks a',
            ]

            for sel in selectors:
                village_list = self.browser.find_elements(By.CSS_SELECTOR, sel)
                if village_list:
                    for elem in village_list:
                        try:
                            href = elem.get_attribute('href') or ''
                            name = elem.text.strip()
                            if not name:
                                continue

                            # Extract village ID from URL (newdid or villageId or did)
                            vid_match = re.search(r'(?:newdid|villageId|did)=(\d+)', href)
                            if vid_match:
                                villages.append({
                                    'id': vid_match.group(1),
                                    'name': name,
                                    'href': href,
                                    'element': elem,
                                })
                        except:
                            continue
                    if villages:
                        break

            # Method 2: Try dropdown/select
            if not villages:
                dropdown = self.browser.find_elements(By.CSS_SELECTOR, 'select option, .villageList option')
                for opt in dropdown:
                    try:
                        vid = opt.get_attribute('value')
                        name = opt.text.strip()
                        if vid and name and vid.isdigit():
                            villages.append({
                                'id': vid,
                                'name': name,
                                'href': f"{config.base_url}/dorf1.php?newdid={vid}",
                                'element': None,
                            })
                    except:
                        continue

            # Method 3: Fallback — add current village
            if not villages:
                current_name = "Main Village"
                name_elem = self.browser.find_element_fast(By.CSS_SELECTOR, '#villageNameField, .villageName')
                if name_elem:
                    current_name = name_elem.text.strip() or current_name

                villages.append({
                    'id': '0',
                    'name': current_name,
                    'href': f"{config.base_url}/dorf1.php",
                    'element': None,
                })

        except Exception as e:
            print(f"Error getting villages: {e}")

        return villages

    def switch_to_village(self, village_id: str) -> bool:
        """Switch to a specific village by ID"""
        from config import config

        try:
            # Method 1: Click the village link directly in the sidebar
            selectors = [
                '#sidebarBoxVillagelist .villageList li a',
                '#sidebarBoxVillagelist a',
                '.villageList a',
                '#villageListLinks a',
            ]

            for sel in selectors:
                links = self.browser.find_elements(By.CSS_SELECTOR, sel)
                for link in links:
                    try:
                        href = link.get_attribute('href') or ''
                        if re.search(rf'(?:newdid|villageId|did)={re.escape(village_id)}(?:\D|$)', href):
                            link.click()
                            time.sleep(0.5)
                            # Verify switch
                            if self._verify_village_switch(village_id):
                                return True
                    except:
                        continue

            # Method 2: Direct URL with newdid
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?newdid={village_id}")
            time.sleep(0.5)
            if self._verify_village_switch(village_id):
                return True

            # Method 3: Try villageId param
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?villageId={village_id}")
            time.sleep(0.5)
            if self._verify_village_switch(village_id):
                return True

            print(f"  Warning: Could not verify village switch to ID {village_id}")
            return False

        except Exception as e:
            print(f"Error switching village: {e}")
            return False

    def _verify_village_switch(self, village_id: str) -> bool:
        """Verify that the village switch actually happened"""
        try:
            # Check URL for village ID
            current_url = self.browser.driver.current_url
            if f'newdid={village_id}' in current_url or f'villageId={village_id}' in current_url:
                return True

            # Check if the active village in sidebar matches
            active = self.browser.find_elements(By.CSS_SELECTOR,
                '#sidebarBoxVillagelist .villageList li.active a, .villageList .active a')
            for elem in active:
                href = elem.get_attribute('href') or ''
                if re.search(rf'(?:newdid|villageId|did)={re.escape(village_id)}(?:\D|$)', href):
                    return True

            # Check page source for village ID reference
            page_source = self.browser.driver.page_source[:5000]
            if f'"villageId":{village_id}' in page_source or f'"did":{village_id}' in page_source:
                return True

            # If we only have one village, it's fine
            village_links = self.browser.find_elements(By.CSS_SELECTOR,
                '#sidebarBoxVillagelist .villageList li a, .villageList a')
            if len(village_links) <= 1:
                return True

        except:
            pass

        return False

    def load_village_training_configs(self) -> Dict[str, VillageTrainingConfig]:
        """Load training configurations for all villages"""
        configs = {}

        try:
            if os.path.exists(self.VILLAGE_CONFIG_FILE):
                with open(self.VILLAGE_CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    for vid, cfg_data in data.items():
                        configs[vid] = VillageTrainingConfig(**cfg_data)
                print(f"✓ Loaded training config for {len(configs)} village(s)")
        except Exception as e:
            print(f"Could not load configs: {e}")

        return configs

    def save_village_training_configs(self, configs: Dict[str, VillageTrainingConfig]):
        """Save training configurations"""
        try:
            data = {vid: asdict(cfg) for vid, cfg in configs.items()}
            with open(self.VILLAGE_CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Could not save configs: {e}")

    def configure_village_training(self, village: Dict) -> Optional[VillageTrainingConfig]:
        """Interactive configuration for a single village's training"""
        print(f"\n{'='*50}")
        print(f"Configuring: {village['name']}")
        print(f"{'='*50}")

        # Switch to the village
        self.switch_to_village(village['id'])
        self.building_cache.clear()  # Clear cache for new village

        config_obj = VillageTrainingConfig(
            village_id=village['id'],
            village_name=village['name']
        )

        # Check barracks
        print(f"\n{'-'*30}")
        print("BARRACKS:")
        if self.navigate_to_barracks():
            available = self.get_available_troops_to_train()

            if available:
                print(f"\nAvailable infantry troops:")
                for i, troop in enumerate(available, 1):
                    max_str = f"(max: {troop['max']})" if troop['max'] > 0 else ""
                    print(f"  {i}. {troop['name']} {max_str}")
                print(f"  0. Skip barracks training")

                choice = input("\nChoose troop to train (number): ").strip()
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(available):
                        selected = available[idx - 1]
                        config_obj.barracks_troop = selected['input_name']
                        config_obj.barracks_troop_name = selected['name']
                        config_obj.train_barracks = True
                        print(f"  ✓ Will train: {selected['name']}")
                    else:
                        config_obj.train_barracks = False
                        print("  Barracks training disabled")
                except ValueError:
                    config_obj.train_barracks = False
            else:
                print("  No troops available in barracks")
                config_obj.train_barracks = False
        else:
            print("  No barracks in this village")
            config_obj.train_barracks = False

        # Check stable
        print(f"\n{'-'*30}")
        print("STABLE:")
        if self.navigate_to_stable():
            available = self.get_available_troops_to_train()

            if available:
                print(f"\nAvailable cavalry troops:")
                for i, troop in enumerate(available, 1):
                    max_str = f"(max: {troop['max']})" if troop['max'] > 0 else ""
                    print(f"  {i}. {troop['name']} {max_str}")
                print(f"  0. Skip stable training")

                choice = input("\nChoose troop to train (number): ").strip()
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(available):
                        selected = available[idx - 1]
                        config_obj.stable_troop = selected['input_name']
                        config_obj.stable_troop_name = selected['name']
                        config_obj.train_stable = True
                        print(f"  ✓ Will train: {selected['name']}")
                    else:
                        config_obj.train_stable = False
                        print("  Stable training disabled")
                except ValueError:
                    config_obj.train_stable = False
            else:
                print("  No troops available in stable")
                config_obj.train_stable = False
        else:
            print("  No stable in this village")
            config_obj.train_stable = False

        return config_obj

    def train_in_village(self, config_obj: VillageTrainingConfig) -> Dict:
        """Train troops in a single village based on its config"""
        result = {
            'village': config_obj.village_name,
            'barracks_trained': 0,
            'stable_trained': 0,
            'success': False
        }

        if not config_obj.enabled:
            return result

        # Switch to village
        self.switch_to_village(config_obj.village_id)
        self.building_cache.clear()

        # Train in barracks
        if config_obj.train_barracks and config_obj.barracks_troop:
            if self.navigate_to_barracks():
                available = self.get_available_troops_to_train()

                for troop in available:
                    if troop['input_name'] == config_obj.barracks_troop:
                        if troop['max'] > 0:
                            if self.train_single_troop(troop, troop['max']):
                                result['barracks_trained'] = troop['max']
                                result['success'] = True
                        break

        # Train in stable
        if config_obj.train_stable and config_obj.stable_troop:
            if self.navigate_to_stable():
                available = self.get_available_troops_to_train()

                for troop in available:
                    if troop['input_name'] == config_obj.stable_troop:
                        if troop['max'] > 0:
                            if self.train_single_troop(troop, troop['max']):
                                result['stable_trained'] = troop['max']
                                result['success'] = True
                        break

        return result

    def multi_village_training_cycle(self, configs: Dict[str, VillageTrainingConfig]) -> Dict:
        """Run one training cycle across all configured villages"""
        results = {
            'villages_trained': 0,
            'total_barracks': 0,
            'total_stable': 0,
        }

        for vid, cfg in configs.items():
            if not cfg.enabled:
                continue

            print(f"\n📍 {cfg.village_name}:")
            village_result = self.train_in_village(cfg)

            if village_result['success']:
                results['villages_trained'] += 1
                results['total_barracks'] += village_result['barracks_trained']
                results['total_stable'] += village_result['stable_trained']

                if village_result['barracks_trained'] > 0:
                    print(f"   🗡️ Barracks: {village_result['barracks_trained']}x {cfg.barracks_troop_name}")
                if village_result['stable_trained'] > 0:
                    print(f"   🐴 Stable: {village_result['stable_trained']}x {cfg.stable_troop_name}")
            else:
                print(f"   No troops trained")

        return results

    def print_training_configs(self, configs: Dict[str, VillageTrainingConfig]):
        """Print current training configurations"""
        if not configs:
            print("No training configurations set up")
            return

        print(f"\n{'Village':<20} {'Status':<8} {'Barracks':<20} {'Stable':<20}")
        print("-" * 70)

        for vid, cfg in configs.items():
            status = "✓ ON" if cfg.enabled else "✗ OFF"
            barracks = cfg.barracks_troop_name if cfg.train_barracks else "-"
            stable = cfg.stable_troop_name if cfg.train_stable else "-"
            print(f"{cfg.village_name:<20} {status:<8} {barracks:<20} {stable:<20}")

    # ==================== SMITHY / ACADEMY / TOWN HALL ====================

    def navigate_to_smithy(self) -> bool:
        """Navigate to smithy"""
        from config import config

        slot = self.find_building_slot(self.SMITHY_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Smithy not found in village")
        return False

    def navigate_to_academy(self) -> bool:
        """Navigate to academy"""
        from config import config

        slot = self.find_building_slot(self.ACADEMY_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Academy not found in village")
        return False

    def navigate_to_town_hall(self) -> bool:
        """Navigate to town hall"""
        from config import config

        slot = self.find_building_slot(self.TOWN_HALL_GID)
        if slot:
            self.browser.navigate_to(f"{config.base_url}/build.php?id={slot}")
            return True

        print("  Town Hall not found in village")
        return False

    def _find_action_buttons(self) -> list:
        """Find clickable action buttons (upgrade/research/celebrate) on the current page.
        Returns list of clickable selenium elements."""
        buttons = []

        # Green action buttons (common across smithy, academy, town hall)
        selectors = [
            'button.green:not([disabled])',
            'button.build:not([disabled])',
            '.research button:not([disabled])',
            '.upgradeButtonsContainer button.green:not([disabled])',
            'form button[type="submit"].green:not([disabled])',
            '.action.green:not([disabled])',
            'a.build:not(.disabled)',
        ]

        for sel in selectors:
            elems = self.browser.find_elements(By.CSS_SELECTOR, sel)
            for elem in elems:
                try:
                    if elem.is_displayed() and elem.is_enabled():
                        buttons.append(elem)
                except:
                    pass

        return buttons

    def upgrade_all_smithy(self) -> int:
        """Upgrade all available troops in the smithy. Returns count of upgrades queued."""
        count = 0

        while True:
            if not self.navigate_to_smithy():
                return count

            time.sleep(0.5)
            buttons = self._find_action_buttons()

            if not buttons:
                print(f"  No more smithy upgrades available")
                break

            try:
                buttons[0].click()
                count += 1
                print(f"  ✓ Smithy upgrade #{count} queued")
                time.sleep(1)
            except Exception as e:
                print(f"  ✗ Could not click upgrade button: {e}")
                break

        return count

    def auto_smithy_loop(self, stop_callback) -> int:
        """Continuously upgrade smithy troops. stop_callback() returns True to stop."""
        total = 0

        while not stop_callback():
            queued = self.upgrade_all_smithy()
            total += queued

            if stop_callback():
                break

            print(f"  Waiting 60s before next smithy check...")
            for _ in range(60):
                if stop_callback():
                    break
                time.sleep(1)

        return total

    def research_all_academy(self) -> int:
        """Research all available troops in the academy. Returns count of researches queued."""
        count = 0

        while True:
            if not self.navigate_to_academy():
                return count

            time.sleep(0.5)
            buttons = self._find_action_buttons()

            if not buttons:
                print(f"  No more academy research available")
                break

            try:
                buttons[0].click()
                count += 1
                print(f"  ✓ Academy research #{count} queued")
                time.sleep(1)
            except Exception as e:
                print(f"  ✗ Could not click research button: {e}")
                break

        return count

    def auto_academy_loop(self, stop_callback) -> int:
        """Continuously research academy troops. stop_callback() returns True to stop."""
        total = 0

        while not stop_callback():
            queued = self.research_all_academy()
            total += queued

            if stop_callback():
                break

            print(f"  Waiting 60s before next academy check...")
            for _ in range(60):
                if stop_callback():
                    break
                time.sleep(1)

        return total

    def start_celebration(self, big: bool = True) -> bool:
        """Start a celebration in the town hall if available.
        big=True for Great Celebration, big=False for Small Celebration."""
        if not self.navigate_to_town_hall():
            return False

        time.sleep(0.5)
        buttons = self._find_action_buttons()

        if not buttons:
            print(f"  No celebration available right now")
            return False

        # Town hall typically shows small celebration first, big celebration second
        # Pick the right button based on preference
        target_idx = -1 if big else 0  # last button = big, first = small

        try:
            if big and len(buttons) >= 2:
                buttons[-1].click()
                print(f"  ✓ Great Celebration started!")
            elif not big:
                buttons[0].click()
                print(f"  ✓ Small Celebration started!")
            else:
                # Only one button available, click it
                buttons[0].click()
                label = "Great" if big else "Small"
                print(f"  ✓ Celebration started (wanted {label}, only one option available)")
            return True
        except Exception as e:
            print(f"  ✗ Could not start celebration: {e}")
            return False

    def auto_celebration_loop(self, stop_callback, big: bool = True, interval: int = 60) -> int:
        """Continuously start celebrations. stop_callback() returns True to stop."""
        total = 0

        while not stop_callback():
            if self.start_celebration(big=big):
                total += 1

            if stop_callback():
                break

            print(f"  Waiting {interval}s before next celebration check...")
            for _ in range(interval):
                if stop_callback():
                    break
                time.sleep(1)

        return total
