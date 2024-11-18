from datetime import datetime
from database import db
from sqlalchemy.dialects.postgresql import JSON

class Persona(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    avatar = db.Column(db.String(128), default='default_avatar')
    personality = db.Column(db.Text, nullable=False)
    interests = db.Column(db.Text, nullable=False)
    goals = db.Column(db.Text, nullable=False)
    behavior_pattern = db.Column(db.String(64), default='balanced')
    interaction_style = db.Column(db.String(64), default='neutral')
    emotional_range = db.Column(db.String(64), default='moderate')
    communication_preference = db.Column(db.String(64), default='direct')
    tags = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New real-world traits
    patience_level = db.Column(db.Integer, default=5)  # 1-10 scale
    attention_to_detail = db.Column(db.Integer, default=5)  # 1-10 scale
    adaptability = db.Column(db.Integer, default=5)  # 1-10 scale
    stress_tolerance = db.Column(db.Integer, default=5)  # 1-10 scale
    organization_skills = db.Column(db.Integer, default=5)  # 1-10 scale
    decision_style = db.Column(db.String(32), default='analytical')  # ['analytical', 'intuitive', 'deliberate', 'spontaneous']
    time_management = db.Column(db.Integer, default=5)  # 1-10 scale
    learning_style = db.Column(db.String(32), default='visual')  # ['visual', 'auditory', 'kinesthetic', 'reading/writing']
    creativity_level = db.Column(db.Integer, default=5)  # 1-10 scale
    risk_tolerance = db.Column(db.Integer, default=5)  # 1-10 scale
    
    interactions_initiated = db.relationship('Interaction', 
                                       foreign_keys='Interaction.initiator_id',
                                       backref='initiator')
    interactions_received = db.relationship('Interaction', 
                                       foreign_keys='Interaction.receiver_id',
                                       backref='receiver')

class Simulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')
    scenario_id = db.Column(db.Integer, db.ForeignKey('scenario.id'))
    interactions = db.relationship('Interaction', backref='simulation')
    scenario = db.relationship('Scenario', backref='simulations')

class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey('simulation.id'))
    initiator_id = db.Column(db.Integer, db.ForeignKey('persona.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('persona.id'))
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    interaction_metadata = db.Column(JSON)  # Renamed from metadata to interaction_metadata

class Scenario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=False)
    context = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(64))
    difficulty = db.Column(db.String(32))
    min_participants = db.Column(db.Integer, default=2)
    max_participants = db.Column(db.Integer)
    duration_minutes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
