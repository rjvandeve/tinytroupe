import os
import json
from openai import OpenAI
from app import logger
from datetime import datetime, timedelta

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
MAX_HISTORY_INTERACTIONS = 5  # Maximum number of previous interactions to include

def validate_persona(persona):
    """Validate persona data before generating interaction."""
    if not persona:
        raise ValueError("Persona object cannot be None")
    
    required_fields = ['name', 'personality', 'interests', 'goals', 'behavior_pattern', 'interaction_style']
    missing_fields = [field for field in required_fields if not getattr(persona, field, None)]
    
    if missing_fields:
        raise ValueError(f"Missing required persona fields: {', '.join(missing_fields)}")

def analyze_potential_conflicts(initiator, receiver):
    """Analyze potential conflicts and tension points between personas."""
    conflicts = []
    
    # Analyze behavior pattern conflicts
    if initiator.behavior_pattern != receiver.behavior_pattern:
        behavior_conflicts = {
            ('proactive', 'reactive'): "Potential tension between proactive and reactive approaches",
            ('analytical', 'creative'): "Possible conflict between analytical and creative thinking styles",
            ('balanced', 'proactive'): "May experience pressure from different pace preferences",
            ('balanced', 'reactive'): "Could face challenges in initiative-taking"
        }
        pattern_pair = tuple(sorted([initiator.behavior_pattern, receiver.behavior_pattern]))
        if pattern_pair in behavior_conflicts:
            conflicts.append(behavior_conflicts[pattern_pair])
    
    # Analyze interaction style conflicts
    interaction_conflicts = {
        ('formal', 'casual'): "Communication style mismatch between formal and casual approaches",
        ('enthusiastic', 'reserved'): "Potential discomfort between enthusiastic and reserved personalities",
        ('neutral', 'formal'): "May experience formality level misalignment",
        ('neutral', 'casual'): "Could face differences in communication expectations"
    }
    style_pair = tuple(sorted([initiator.interaction_style, receiver.interaction_style]))
    if style_pair in interaction_conflicts:
        conflicts.append(interaction_conflicts[style_pair])
    
    # Analyze communication preference conflicts
    if hasattr(initiator, 'communication_preference') and hasattr(receiver, 'communication_preference'):
        comm_conflicts = {
            ('direct', 'diplomatic'): "Tension between direct and diplomatic communication styles",
            ('detailed', 'concise'): "Potential conflict in information exchange preferences",
            ('storytelling', 'direct'): "May struggle with different narrative approaches",
            ('concise', 'storytelling'): "Could face challenges in communication depth"
        }
        comm_pair = tuple(sorted([initiator.communication_preference, receiver.communication_preference]))
        if comm_pair in comm_conflicts:
            conflicts.append(comm_conflicts[comm_pair])
    
    # Analyze personality-based conflicts
    personality_keywords = {
        'competitive': ['ambitious', 'driven', 'assertive'],
        'collaborative': ['cooperative', 'team-oriented', 'supportive'],
        'analytical': ['logical', 'methodical', 'systematic'],
        'creative': ['innovative', 'artistic', 'imaginative']
    }
    
    initiator_traits = set(word.lower() for word in initiator.personality.split())
    receiver_traits = set(word.lower() for word in receiver.personality.split())
    
    for trait_category, keywords in personality_keywords.items():
        if any(word in initiator_traits for word in keywords) and \
           any(word in receiver_traits for word in keywords) and \
           trait_category in ['competitive', 'analytical']:
            conflicts.append(f"Potential competition/conflict in {trait_category} approaches")
    
    # Analyze goal alignment and conflicts
    initiator_goals = set(initiator.goals.lower().split())
    receiver_goals = set(receiver.goals.lower().split())
    
    # Check for competing goals
    competing_keywords = {'lead', 'control', 'direct', 'manage', 'decide'}
    if initiator_goals.intersection(competing_keywords) and receiver_goals.intersection(competing_keywords):
        conflicts.append("Competing leadership or control objectives")
    
    # Check for goal misalignment
    if not initiator_goals.intersection(receiver_goals):
        conflicts.append("Significantly different goals and objectives")
    
    return conflicts

def format_dialogue(interaction_data):
    """Format dialogue content consistently."""
    try:
        if isinstance(interaction_data.get('dialogue'), dict):
            dialogue_text = []
            for speaker, text in interaction_data['dialogue'].items():
                if isinstance(text, dict) and 'text' in text:
                    dialogue_text.append(f"{speaker}: {text['text']}")
                else:
                    dialogue_text.append(f"{speaker}: {text}")
            return "\n".join(dialogue_text)
        return str(interaction_data.get('dialogue', ''))
    except Exception as e:
        logger.error(f"Error formatting dialogue: {str(e)}")
        return str(interaction_data.get('dialogue', ''))

def get_recent_interactions(simulation_id, initiator_id, receiver_id):
    """Get recent interactions between the personas in the simulation."""
    from models import Interaction
    from app import db
    
    recent = (Interaction.query
             .filter(Interaction.simulation_id == simulation_id)
             .filter(((Interaction.initiator_id == initiator_id) & 
                     (Interaction.receiver_id == receiver_id)) |
                    ((Interaction.initiator_id == receiver_id) & 
                     (Interaction.receiver_id == initiator_id)))
             .order_by(Interaction.timestamp.desc())
             .limit(MAX_HISTORY_INTERACTIONS)
             .all())
    
    return [
        {
            'initiator': interaction.initiator.name,
            'receiver': interaction.receiver.name,
            'content': interaction.content,
            'timestamp': interaction.timestamp,
            'metadata': interaction.interaction_metadata
        }
        for interaction in reversed(recent)
    ]

def format_conversation_history(history):
    """Format conversation history for the prompt."""
    if not history:
        return ""
    
    formatted = "\nPrevious interactions:\n"
    for interaction in history:
        formatted += f"[{interaction['timestamp'].strftime('%H:%M:%S')}]\n"
        formatted += f"Content: {interaction['content']}\n"
        if interaction.get('metadata'):
            formatted += f"Outcome: {interaction['metadata'].get('outcome', {}).get('resolution_status', 'unknown')}\n"
            formatted += f"Impact: {interaction['metadata'].get('outcome', {}).get('relationship_impact', 'unknown')}\n"
        formatted += "---\n"
    return formatted

def generate_interaction(initiator, receiver, context, simulation_id=None, retry_count=0):
    """Generate interaction between two personas with enhanced analysis and conflict tracking."""
    try:
        # Validate input personas
        validate_persona(initiator)
        validate_persona(receiver)
        
        logger.info(f"Generating interaction between {initiator.name} and {receiver.name}")
        
        # Analyze potential conflicts with enhanced detection
        conflicts = analyze_potential_conflicts(initiator, receiver)
        
        # Get conversation history if simulation_id is provided
        conversation_history = ""
        if simulation_id:
            history = get_recent_interactions(simulation_id, initiator.id, receiver.id)
            conversation_history = format_conversation_history(history)
        
        prompt = f'''
        Generate a detailed dialogue interaction between two personas with the following characteristics and potential conflicts:

        Context: {context}
        {conversation_history}
        
        Initiator: {initiator.name}
        Personality: {initiator.personality}
        Interests: {initiator.interests}
        Goals: {initiator.goals}
        Behavior Pattern: {initiator.behavior_pattern}
        Interaction Style: {initiator.interaction_style}
        Communication Preference: {initiator.communication_preference}

        Receiver: {receiver.name}
        Personality: {receiver.personality}
        Interests: {receiver.interests}
        Goals: {receiver.goals}
        Behavior Pattern: {receiver.behavior_pattern}
        Interaction Style: {receiver.interaction_style}
        Communication Preference: {receiver.communication_preference}

        Identified Potential Conflicts:
        {chr(10).join(f"- {conflict}" for conflict in conflicts)}

        Consider these aspects in the interaction:
        1. Natural development of tension points based on identified conflicts
        2. Realistic personality clashes and their manifestation
        3. Impact of different communication styles on understanding
        4. Progressive relationship development or strain
        5. Resolution attempts and their effectiveness
        
        Return a JSON object with the following structure:
        {{
            "dialogue": "Format as: [Name]: [Message]\\n[Name]: [Response]",
            "sentiment": "positive/neutral/negative",
            "outcome": {{
                "resolution_status": "resolved/partially_resolved/unresolved",
                "agreement_level": "full/partial/none",
                "key_points": ["List of main points discussed"],
                "tension_points": ["List of areas where conflict or disagreement occurred"],
                "relationship_impact": "strengthened/strained/unchanged"
            }},
            "analysis": {{
                "interaction_quality": "1-10 score",
                "communication_effectiveness": "1-10 score",
                "conflict_intensity": "1-10 score",
                "resolution_quality": "1-10 score"
            }}
        }}
        '''
        
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a persona interaction simulator. Generate natural dialogue between two personas within the given scenario context, maintaining conversation continuity and relationship development. Always respond with valid JSON that includes detailed interaction analysis."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        # Extract and validate response
        if not response.choices:
            raise ValueError("Empty response from OpenAI API")
            
        response_text = response.choices[0].message.content.strip()
        logger.debug(f"Raw API response: {response_text}")
        
        try:
            interaction_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}\nResponse text: {response_text}")
            if retry_count < MAX_RETRIES:
                logger.info(f"Retrying interaction generation (attempt {retry_count + 1}/{MAX_RETRIES})")
                return generate_interaction(initiator, receiver, context, simulation_id, retry_count + 1)
            raise
        
        # Format dialogue content
        interaction_data['dialogue'] = format_dialogue(interaction_data)
        
        # Validate required fields
        if not interaction_data.get('dialogue'):
            raise ValueError("Generated interaction missing dialogue content")
        if not isinstance(interaction_data.get('outcome'), dict):
            raise ValueError("Generated interaction missing outcome analysis")
        if not isinstance(interaction_data.get('analysis'), dict):
            raise ValueError("Generated interaction missing detailed analysis")
            
        return interaction_data
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error in generate_interaction: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Validation error in generate_interaction: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in generate_interaction: {str(e)}")
        if retry_count < MAX_RETRIES:
            logger.info(f"Retrying interaction generation (attempt {retry_count + 1}/{MAX_RETRIES})")
            return generate_interaction(initiator, receiver, context, simulation_id, retry_count + 1)
        raise
