import random
from app import db, app
from models import Persona
from datetime import datetime

# Lists of characteristics for generating diverse personas
FIRST_NAMES = [
    "James", "Emma", "Liam", "Olivia", "Noah", "Ava", "William", "Isabella", "Oliver", "Sophia",
    "Aiden", "Mia", "Lucas", "Charlotte", "Mason", "Amelia", "Ethan", "Harper", "Alexander", "Evelyn",
    "Wei", "Yuki", "Mohammad", "Priya", "Juan", "Sofia", "Pavel", "Fatima", "Diego", "Nina",
    "Raj", "Zara", "Chen", "Aisha", "Hassan", "Maya", "Luis", "Elena", "Dmitri", "Ana"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Chen", "Wong", "Kim", "Singh", "Patel", "Kumar", "Ali", "Khan", "Nguyen", "Lee",
    "Wang", "Liu", "Zhang", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin",
    "Gonzalez", "Hernandez", "Lopez", "Perez", "Sanchez", "Ramirez", "Torres", "Flores", "Rivera", "Collins"
]

AVATAR_STYLES = ["professional", "casual", "artistic", "technical", "friendly"]

PERSONALITY_TRAITS = [
    "analytical", "creative", "diplomatic", "energetic", "focused",
    "generous", "helpful", "innovative", "jovial", "knowledgeable",
    "logical", "methodical", "nurturing", "optimistic", "patient",
    "quick-thinking", "reliable", "systematic", "thoughtful", "understanding"
]

INTERESTS = [
    "technology", "art", "science", "literature", "music",
    "sports", "travel", "cooking", "photography", "nature",
    "history", "philosophy", "mathematics", "languages", "business",
    "engineering", "medicine", "education", "environment", "psychology"
]

GOALS = [
    "professional development", "creative expression", "knowledge acquisition",
    "skill mastery", "community building", "innovation", "leadership",
    "research advancement", "teaching others", "problem solving",
    "project management", "team collaboration", "process improvement",
    "strategic planning", "relationship building"
]

BEHAVIOR_PATTERNS = ["balanced", "proactive", "reactive", "analytical", "creative"]

INTERACTION_STYLES = ["neutral", "formal", "casual", "enthusiastic", "reserved"]

EMOTIONAL_RANGES = ["moderate", "expressive", "controlled", "volatile", "stable"]

COMMUNICATION_PREFERENCES = ["direct", "diplomatic", "detailed", "concise", "storytelling"]

TAG_CATEGORIES = [
    "industry", "expertise", "skills", "interests", "approach",
    "background", "specialization", "experience", "role", "focus"
]

INDUSTRY_TAGS = [
    "healthcare", "technology", "finance", "education", "manufacturing",
    "retail", "consulting", "research", "media", "nonprofit"
]

def generate_persona_description(traits):
    """Generate a coherent personality description based on selected traits."""
    return f"A {', '.join(traits[:3])} individual who approaches challenges with {traits[3]} thinking and demonstrates {traits[4]} tendencies in professional settings."

def generate_interests_description(selected_interests):
    """Generate a detailed interests description."""
    primary = random.sample(selected_interests, 2)
    secondary = random.sample([i for i in selected_interests if i not in primary], 2)
    return f"Primarily focused on {' and '.join(primary)}, with additional interests in {' and '.join(secondary)}."

def generate_goals_description(selected_goals):
    """Generate a meaningful goals description."""
    main_goals = random.sample(selected_goals, 2)
    return f"Aims to excel in {main_goals[0]} while contributing to {main_goals[1]}. Committed to continuous improvement and professional growth."

def generate_tags(industry):
    """Generate relevant tags for the persona."""
    tags = [industry]
    potential_tags = random.sample(INTERESTS + list(set(PERSONALITY_TRAITS)), 3)
    tags.extend(potential_tags)
    return ','.join(tags)

def create_diverse_personas(count=500):
    """Create diverse personas with varying characteristics."""
    created_count = 0
    
    with app.app_context():
        try:
            for _ in range(count):
                # Generate basic information
                first_name = random.choice(FIRST_NAMES)
                last_name = random.choice(LAST_NAMES)
                name = f"{first_name} {last_name}"
                
                # Generate personality traits and descriptions
                traits = random.sample(PERSONALITY_TRAITS, 5)
                selected_interests = random.sample(INTERESTS, 6)
                selected_goals = random.sample(GOALS, 4)
                industry = random.choice(INDUSTRY_TAGS)
                
                persona = Persona(
                    name=name,
                    avatar=random.choice(AVATAR_STYLES),
                    personality=generate_persona_description(traits),
                    interests=generate_interests_description(selected_interests),
                    goals=generate_goals_description(selected_goals),
                    behavior_pattern=random.choice(BEHAVIOR_PATTERNS),
                    interaction_style=random.choice(INTERACTION_STYLES),
                    emotional_range=random.choice(EMOTIONAL_RANGES),
                    communication_preference=random.choice(COMMUNICATION_PREFERENCES),
                    tags=generate_tags(industry),
                    created_at=datetime.utcnow()
                )
                
                db.session.add(persona)
                created_count += 1
                
                # Commit in batches to avoid memory issues
                if created_count % 50 == 0:
                    db.session.commit()
            
            # Final commit for any remaining personas
            db.session.commit()
            print(f"Successfully created {created_count} diverse personas")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating personas: {str(e)}")
            raise

if __name__ == "__main__":
    create_diverse_personas()
