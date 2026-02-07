"""
Task Queue Module - Sequential task execution for Travian bot
Since Selenium can only do one thing at a time, tasks run in sequence.
"""

import re
import time
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from selenium.webdriver.common.by import By


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class Task:
    id: int
    name: str
    task_type: str  # 'train', 'upgrade', 'attack', etc.
    config: Dict  # Task-specific configuration
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    runs: int = 0
    last_run: str = ""
    repeat: bool = True  # Should this task repeat?
    interval: int = 30  # Seconds between runs


class TaskQueue:
    """
    Manages a queue of tasks that run sequentially.
    Tasks are executed one at a time in round-robin fashion.
    """

    def __init__(self):
        self.tasks: Dict[int, Task] = {}
        self.task_counter = 0
        self.running = False
        self.current_task_id: Optional[int] = None
        self.stop_flag = threading.Event()

    def add_task(self, name: str, task_type: str, config: Dict, repeat: bool = True, interval: int = 30) -> int:
        """Add a new task to the queue"""
        self.task_counter += 1
        task = Task(
            id=self.task_counter,
            name=name,
            task_type=task_type,
            config=config,
            created_at=time.strftime('%H:%M:%S'),
            repeat=repeat,
            interval=interval
        )
        self.tasks[task.id] = task
        print(f"✓ Task #{task.id} added: {name}")
        return task.id

    def remove_task(self, task_id: int) -> bool:
        """Remove a task from the queue"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def pause_task(self, task_id: int) -> bool:
        """Pause a task"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.PAUSED
            return True
        return False

    def resume_task(self, task_id: int) -> bool:
        """Resume a paused task"""
        if task_id in self.tasks and self.tasks[task_id].status == TaskStatus.PAUSED:
            self.tasks[task_id].status = TaskStatus.PENDING
            return True
        return False

    def get_next_task(self) -> Optional[Task]:
        """Get the next pending task to run"""
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        return list(self.tasks.values())

    def get_active_tasks(self) -> List[Task]:
        """Get tasks that are pending or running"""
        return [t for t in self.tasks.values() if t.status in [TaskStatus.PENDING, TaskStatus.RUNNING]]

    def stop_all(self):
        """Stop all tasks"""
        self.stop_flag.set()
        for task in self.tasks.values():
            if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                task.status = TaskStatus.STOPPED

    def clear_completed(self):
        """Remove completed/stopped tasks"""
        to_remove = [tid for tid, t in self.tasks.items()
                     if t.status in [TaskStatus.COMPLETED, TaskStatus.STOPPED, TaskStatus.FAILED]]
        for tid in to_remove:
            del self.tasks[tid]

    def mark_task_done(self, task_id: int, success: bool = True):
        """Mark a task run as complete"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.runs += 1
            task.last_run = time.strftime('%H:%M:%S')

            if task.repeat:
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED


class TaskExecutor:
    """
    Executes tasks from the queue using the bot's modules.
    """

    def __init__(self, bot):
        self.bot = bot
        self.queue = TaskQueue()
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def add_train_task(self, building: str, troop_name: str, troop_input: str, interval: int = 30) -> int:
        """Add a troop training task"""
        return self.queue.add_task(
            name=f"Train {troop_name}",
            task_type="train",
            config={
                'building': building,
                'troop_name': troop_name,
                'troop_input': troop_input
            },
            repeat=True,
            interval=interval
        )

    def add_upgrade_task(self, field_ids: List[int] = None, target_level: int = 20, interval: int = 30) -> int:
        """Add a resource upgrade task"""
        return self.queue.add_task(
            name=f"Upgrade resources to L{target_level}",
            task_type="upgrade",
            config={
                'field_ids': field_ids or list(range(1, 19)),
                'target_level': target_level
            },
            repeat=True,
            interval=interval
        )

    def add_village_upgrade_task(self, target_level: int = 20, interval: int = 30) -> int:
        """Add a village building upgrade task"""
        return self.queue.add_task(
            name=f"Upgrade village buildings to L{target_level}",
            task_type="village_upgrade",
            config={
                'target_level': target_level
            },
            repeat=True,
            interval=interval
        )

    def add_farming_task(self, interval: int = 300) -> int:
        """Add an automated farming task"""
        return self.queue.add_task(
            name=f"Auto-farm (every {interval}s)",
            task_type="farm",
            config={},
            repeat=True,
            interval=interval
        )

    def add_multi_village_train_task(self, interval: int = 60) -> int:
        """Add a multi-village training task"""
        return self.queue.add_task(
            name=f"Train all villages (every {interval}s)",
            task_type="multi_village_train",
            config={},
            repeat=True,
            interval=interval
        )

    def add_all_villages_upgrade_task(self, target_level: int = 20, interval: int = 60) -> int:
        """Add a task to upgrade resources in ALL villages"""
        return self.queue.add_task(
            name=f"Upgrade resources ALL villages to L{target_level}",
            task_type="all_villages_upgrade",
            config={'target_level': target_level},
            repeat=True,
            interval=interval
        )

    def add_all_villages_building_task(self, target_level: int = 20, interval: int = 60) -> int:
        """Add a task to upgrade village buildings in ALL villages"""
        return self.queue.add_task(
            name=f"Upgrade buildings ALL villages to L{target_level}",
            task_type="all_villages_building",
            config={'target_level': target_level},
            repeat=True,
            interval=interval
        )

    def add_all_villages_smart_build_task(self, interval: int = 120) -> int:
        """Add a smart build task for ALL villages"""
        return self.queue.add_task(
            name=f"Smart build ALL villages",
            task_type="all_villages_smart_build",
            config={},
            repeat=True,
            interval=interval
        )

    def execute_task(self, task: Task) -> bool:
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        success = False

        try:
            if task.task_type == "train":
                success = self._execute_train(task.config)
            elif task.task_type == "upgrade":
                success = self._execute_upgrade(task.config)
            elif task.task_type == "village_upgrade":
                success = self._execute_village_upgrade(task.config)
            elif task.task_type == "farm":
                success = self._execute_farm(task.config)
            elif task.task_type == "multi_village_train":
                success = self._execute_multi_village_train(task.config)
            elif task.task_type == "all_villages_upgrade":
                success = self._execute_all_villages_upgrade(task.config)
            elif task.task_type == "all_villages_building":
                success = self._execute_all_villages_building(task.config)
            elif task.task_type == "all_villages_smart_build":
                success = self._execute_all_villages_smart_build(task.config)
            else:
                print(f"  Unknown task type: {task.task_type}")
        except Exception as e:
            print(f"  Task error: {e}")
            success = False

        self.queue.mark_task_done(task.id, success)
        return success

    def _execute_train(self, config: Dict) -> bool:
        """Execute training task"""
        building = config['building']
        troop_name = config['troop_name']
        troop_input = config['troop_input']

        # Navigate to building
        if building == 'barracks':
            if not self.bot.military.navigate_to_barracks():
                return False
        elif building == 'stable':
            if not self.bot.military.navigate_to_stable():
                return False

        # Find the troop and train
        available = self.bot.military.get_available_troops_to_train()
        for troop in available:
            if troop['input_name'] == troop_input or troop_name in troop['name']:
                if troop['max'] > 0:
                    return self.bot.military.train_single_troop(troop, troop['max'])
        return False

    def _execute_upgrade(self, config: Dict) -> bool:
        """Execute upgrade task - upgrades ONE field per run"""
        field_ids = config['field_ids']
        target_level = config['target_level']

        # Try to upgrade one field
        for field_id in field_ids:
            self.bot.buildings.navigate_to_building(field_id)

            # Get current level
            h1 = self.bot.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            current_level = 0
            name = f"Field #{field_id}"

            if h1:
                text = h1.text
                if 'Level' in text:
                    name = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        current_level = int(match.group(1))

            # Skip if already at target level
            if current_level >= target_level:
                continue

            # Try to click upgrade
            try:
                upgrade_btn = self.bot.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                if upgrade_btn:
                    btn_class = upgrade_btn.get_attribute('class') or ''
                    if 'disabled' not in btn_class:
                        print(f"  🔨 {name} L{current_level} -> L{current_level + 1}")
                        upgrade_btn.click()
                        return True
            except:
                pass

        return False

    def _execute_village_upgrade(self, config: Dict) -> bool:
        """Execute village building upgrade task - upgrades ONE building per run"""
        target_level = config['target_level']

        # Scan and try to upgrade village buildings (19-40)
        for building_id in range(19, 41):
            self.bot.buildings.navigate_to_building(building_id)

            # Get current level and name
            h1 = self.bot.browser.find_element_fast(By.CSS_SELECTOR, 'h1.titleInHeader')
            current_level = 0
            name = "Empty"

            if h1:
                text = h1.text
                if 'Level' in text:
                    name = text.split('Level')[0].strip()
                    match = re.search(r'Level\s*(\d+)', text)
                    if match:
                        current_level = int(match.group(1))
                elif text.strip() and 'Construct' not in text:
                    name = text.strip()

            # Skip empty slots or already maxed
            if name in ['Empty', 'Unknown'] or 'Construct' in name:
                continue
            if current_level >= target_level:
                continue

            # Try to click upgrade
            try:
                upgrade_btn = self.bot.browser.find_element_fast(By.CSS_SELECTOR, 'button.build')
                if upgrade_btn:
                    btn_class = upgrade_btn.get_attribute('class') or ''
                    if 'disabled' not in btn_class:
                        print(f"  🏗️ {name} L{current_level} -> L{current_level + 1}")
                        upgrade_btn.click()
                        return True
            except:
                pass

        return False

    def _execute_farm(self, config: Dict) -> bool:
        """Execute farming task - send raids to all enabled farms"""
        if hasattr(self.bot, 'farming') and self.bot.farming:
            results = self.bot.farming.send_all_raids()
            return results['sent'] > 0
        else:
            print("  ✗ Farming module not initialized")
            return False

    def _execute_multi_village_train(self, config: Dict) -> bool:
        """Execute multi-village training task"""
        if hasattr(self.bot, 'military') and self.bot.military:
            # Load training configs
            configs = self.bot.military.load_village_training_configs()
            if not configs:
                print("  ✗ No village training configs set up")
                return False

            results = self.bot.military.multi_village_training_cycle(configs)
            return results['villages_trained'] > 0
        else:
            print("  ✗ Military module not initialized")
            return False

    def _execute_all_villages_upgrade(self, config: Dict) -> bool:
        """Execute resource upgrade in ALL villages - fully completes each village before moving to next"""
        if not hasattr(self.bot, 'village_cycler') or not self.bot.village_cycler:
            print("  ✗ Village cycler not initialized")
            return False

        villages = self.bot.village_cycler.get_all_villages()
        if not villages:
            print("  ✗ No villages found")
            return False

        total_upgrades = 0
        start_village = self.bot.village_cycler.get_current_village()

        # Track which village we're working on (persists between task runs)
        if not hasattr(self, '_current_village_index'):
            self._current_village_index = 0

        # Get current village to work on
        if self._current_village_index >= len(villages):
            self._current_village_index = 0  # Start over

        village = villages[self._current_village_index]
        print(f"  [{village['name']}] (village {self._current_village_index + 1}/{len(villages)})")

        if not self.bot.village_cycler.switch_to_village(village['id']):
            print(f"    Failed to switch, trying next village")
            self._current_village_index += 1
            return False

        # Run full resource upgrade for this village
        upgrades = self.bot.buildings.auto_upgrade_all_to_20(self.bot.session, lambda: False)
        total_upgrades += upgrades

        if upgrades == 0:
            # This village is done, move to next
            print(f"    ✓ Village complete, moving to next")
            self._current_village_index += 1

        # Return to start village
        if start_village['id']:
            self.bot.village_cycler.switch_to_village(start_village['id'])

        return total_upgrades > 0

    def _execute_all_villages_building(self, config: Dict) -> bool:
        """Execute village building upgrade in ALL villages - fully completes each village before moving to next"""
        if not hasattr(self.bot, 'village_cycler') or not self.bot.village_cycler:
            print("  ✗ Village cycler not initialized")
            return False

        villages = self.bot.village_cycler.get_all_villages()
        if not villages:
            print("  ✗ No villages found")
            return False

        total_upgrades = 0
        start_village = self.bot.village_cycler.get_current_village()

        # Track which village we're working on
        if not hasattr(self, '_building_village_index'):
            self._building_village_index = 0

        if self._building_village_index >= len(villages):
            self._building_village_index = 0

        village = villages[self._building_village_index]
        print(f"  [{village['name']}] (village {self._building_village_index + 1}/{len(villages)})")

        if not self.bot.village_cycler.switch_to_village(village['id']):
            print(f"    Failed to switch, trying next village")
            self._building_village_index += 1
            return False

        # Run full building upgrade for this village
        upgrades = self.bot.buildings.auto_upgrade_all_buildings(self.bot.session, lambda: False)
        total_upgrades += upgrades

        if upgrades == 0:
            print(f"    ✓ Village complete, moving to next")
            self._building_village_index += 1

        if start_village['id']:
            self.bot.village_cycler.switch_to_village(start_village['id'])

        return total_upgrades > 0

    def _execute_all_villages_smart_build(self, config: Dict) -> bool:
        """Execute smart build in ALL villages - fully completes each village before moving to next"""
        if not hasattr(self.bot, 'village_cycler') or not self.bot.village_cycler:
            print("  ✗ Village cycler not initialized")
            return False

        villages = self.bot.village_cycler.get_all_villages()
        if not villages:
            print("  ✗ No villages found")
            return False

        total_upgrades = 0
        start_village = self.bot.village_cycler.get_current_village()

        # Track which village we're working on
        if not hasattr(self, '_smart_build_village_index'):
            self._smart_build_village_index = 0

        if self._smart_build_village_index >= len(villages):
            self._smart_build_village_index = 0

        village = villages[self._smart_build_village_index]
        print(f"  [{village['name']}] (village {self._smart_build_village_index + 1}/{len(villages)})")

        if not self.bot.village_cycler.switch_to_village(village['id']):
            print(f"    Failed to switch, trying next village")
            self._smart_build_village_index += 1
            return False

        # Run full smart build for this village
        upgrades = self.bot.buildings.smart_build_order(lambda: False)
        total_upgrades += upgrades

        if upgrades == 0:
            print(f"    ✓ Village complete, moving to next")
            self._smart_build_village_index += 1

        if start_village['id']:
            self.bot.village_cycler.switch_to_village(start_village['id'])

        return total_upgrades > 0

    def run_loop(self, stop_event: threading.Event):
        """Main task execution loop"""
        print("\n🔄 Task executor started")

        while not stop_event.is_set():
            task = self.queue.get_next_task()

            if task:
                print(f"\n⏳ Running: {task.name}")
                self.execute_task(task)

                # Wait the task's interval before it can run again
                for _ in range(task.interval):
                    if stop_event.is_set():
                        break
                    time.sleep(1)
            else:
                # No tasks ready, wait a bit
                time.sleep(1)

        print("\n🛑 Task executor stopped")

    def start(self) -> bool:
        """Start the task executor in a thread"""
        if self.running:
            return False

        self.running = True
        self.queue.stop_flag.clear()
        self.thread = threading.Thread(target=self.run_loop, args=(self.queue.stop_flag,), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop the task executor"""
        self.running = False
        self.queue.stop_all()
