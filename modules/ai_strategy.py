import os
from typing import Dict, List, Optional
from anthropic import Anthropic


class AIStrategist:
    """AI-powered decision making for game strategy"""

    def __init__(self):
        self.client = None
        api_key = os.getenv('ANTHROPIC_API_KEY')

        if api_key and api_key != 'your_api_key_here':
            try:
                self.client = Anthropic(api_key=api_key)
                print("✓ AI Strategist initialized with Claude API")
            except Exception as e:
                print(f"⚠️  AI Strategist could not initialize: {e}")
                self.client = None
        else:
            print("⚠️  No Anthropic API key found - AI features disabled")

    def is_available(self) -> bool:
        """Check if AI features are available"""
        return self.client is not None

    def analyze_game_state(self, game_data: Dict) -> Dict:
        """Analyze current game state and provide strategic recommendations"""
        if not self.is_available():
            return self._fallback_strategy(game_data)

        try:
            # Prepare game state summary
            prompt = self._create_strategy_prompt(game_data)

            # Call Claude API
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text

            # Parse response into actionable recommendations
            return self._parse_ai_response(response_text)

        except Exception as e:
            print(f"✗ AI analysis error: {e}")
            return self._fallback_strategy(game_data)

    def _create_strategy_prompt(self, game_data: Dict) -> str:
        """Create a prompt for the AI to analyze game state"""
        resources = game_data.get('resources', {})
        production = game_data.get('production', {})
        buildings = game_data.get('buildings', [])
        troops = game_data.get('troops', {})

        prompt = f"""You are an expert Travian strategy advisor. Analyze the current game state and provide specific recommendations.

Current Game State:
- Resources: Wood={resources.get('wood', 0)}, Clay={resources.get('clay', 0)}, Iron={resources.get('iron', 0)}, Crop={resources.get('crop', 0)}
- Production: Wood={production.get('wood', 0)}/h, Clay={production.get('clay', 0)}/h, Iron={production.get('iron', 0)}/h, Crop={production.get('crop', 0)}/h
- Buildings: {len(buildings)} built
- Troops: {troops}

Please provide:
1. Priority building recommendations (which buildings to upgrade/build next)
2. Resource management advice
3. Military strategy (troop training priorities)
4. Overall strategic priorities for the next phase

Keep your response concise and actionable."""

        return prompt

    def _parse_ai_response(self, response: str) -> Dict:
        """Parse AI response into structured recommendations"""
        return {
            'building_priority': ['Main Building', 'Cropland', 'Warehouse'],
            'troop_priority': ['Infantry'],
            'strategy': response,
            'urgent_actions': []
        }

    def _fallback_strategy(self, game_data: Dict) -> Dict:
        """Fallback strategy when AI is not available"""
        # Simple rule-based strategy
        resources = game_data.get('resources', {})
        production = game_data.get('production', {})

        recommendations = {
            'building_priority': [],
            'troop_priority': [],
            'strategy': 'Using basic rule-based strategy',
            'urgent_actions': []
        }

        # Early game: focus on resource production
        if all(production.get(r, 0) < 100 for r in ['wood', 'clay', 'iron', 'crop']):
            recommendations['building_priority'] = ['Cropland', 'Woodcutter', 'Clay Pit', 'Iron Mine']
            recommendations['strategy'] = 'Early game: Focus on resource production'

        # Mid game: balance resources and military
        elif all(production.get(r, 0) < 500 for r in ['wood', 'clay', 'iron', 'crop']):
            recommendations['building_priority'] = ['Main Building', 'Barracks', 'Warehouse', 'Granary']
            recommendations['troop_priority'] = ['Basic Infantry']
            recommendations['strategy'] = 'Mid game: Balance economy and military'

        # Check for storage issues
        storage_capacity = game_data.get('storage_capacity', {})
        for resource in ['wood', 'clay', 'iron']:
            if resources.get(resource, 0) > storage_capacity.get(resource, 1000) * 0.8:
                recommendations['urgent_actions'].append(f'Upgrade Warehouse - {resource} storage nearly full')

        if resources.get('crop', 0) > storage_capacity.get('crop', 1000) * 0.8:
            recommendations['urgent_actions'].append('Upgrade Granary - crop storage nearly full')

        return recommendations

    def should_build_now(self, building_name: str, game_data: Dict) -> bool:
        """Decide if a building should be built now"""
        resources = game_data.get('resources', {})

        # Simple rules
        if building_name == 'Warehouse' and any(
            resources.get(r, 0) > game_data.get('storage_capacity', {}).get(r, 1000) * 0.7
            for r in ['wood', 'clay', 'iron']
        ):
            return True

        if building_name == 'Granary' and resources.get('crop', 0) > \
                game_data.get('storage_capacity', {}).get('crop', 1000) * 0.7:
            return True

        return False

    def should_train_troops(self, game_data: Dict) -> bool:
        """Decide if troops should be trained now"""
        resources = game_data.get('resources', {})
        production = game_data.get('production', {})

        # Don't train if resources are very low
        if all(resources.get(r, 0) < 200 for r in ['wood', 'clay', 'iron', 'crop']):
            return False

        # Don't train if crop production is negative or very low
        if production.get('crop', 0) < 5:
            return False

        return True

    def get_next_action(self, game_data: Dict) -> Optional[Dict]:
        """Get the next recommended action"""
        recommendations = self.analyze_game_state(game_data)

        # Check urgent actions first
        if recommendations.get('urgent_actions'):
            return {
                'type': 'urgent',
                'action': recommendations['urgent_actions'][0]
            }

        # Then building priorities
        if recommendations.get('building_priority'):
            return {
                'type': 'build',
                'target': recommendations['building_priority'][0]
            }

        # Then military
        if recommendations.get('troop_priority') and self.should_train_troops(game_data):
            return {
                'type': 'train',
                'target': recommendations['troop_priority'][0]
            }

        return None
