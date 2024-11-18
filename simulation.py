import random
from datetime import datetime
import eventlet
from app import app, db, socketio, logger
from models import Simulation, Interaction, Persona
from chat_request import generate_interaction
from sqlalchemy.exc import SQLAlchemyError
import time

class SimulationManager:
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    
    def __init__(self, simulation_id, persona_ids=None):
        self.simulation_id = simulation_id
        self.is_running = False
        self.greenthread = None
        self.error_count = 0
        self.max_errors = 5
        self.simulation = None
        self.custom_context = None
        self.selected_persona_ids = persona_ids or []
        self._load_simulation()
    
    def _load_simulation(self):
        """Load simulation data with validation."""
        try:
            with app.app_context():
                simulation = Simulation.query.get(self.simulation_id)
                if not simulation:
                    raise ValueError(f"Simulation with ID {self.simulation_id} not found")
                self.simulation = simulation
                logger.info(f"Loaded simulation: {simulation.name} (ID: {self.simulation_id})")
        except SQLAlchemyError as e:
            logger.error(f"Database error loading simulation: {str(e)}")
            raise
    
    def validate_personas(self):
        """Validate that enough selected personas exist for simulation."""
        try:
            with app.app_context():
                if not self.selected_persona_ids:
                    persona_count = Persona.query.count()
                    if persona_count < 2:
                        raise ValueError(f"Insufficient personas for simulation (found {persona_count}, need at least 2)")
                else:
                    selected_count = Persona.query.filter(Persona.id.in_(self.selected_persona_ids)).count()
                    if selected_count < 2:
                        raise ValueError(f"Insufficient selected personas for simulation (found {selected_count}, need at least 2)")
                    if selected_count != len(self.selected_persona_ids):
                        raise ValueError("Some selected personas do not exist in the database")
                return True
        except SQLAlchemyError as e:
            logger.error(f"Database error validating personas: {str(e)}")
            raise
            
    def start_simulation(self):
        """Start the simulation with improved error handling."""
        try:
            # Validate simulation state
            if self.is_running:
                raise ValueError("Simulation is already running")
                
            # Validate personas
            self.validate_personas()
            
            with app.app_context():
                if not self.simulation:
                    self._load_simulation()
                    
                # Update simulation state
                sim = self.simulation
                sim.status = 'running'
                sim.start_time = datetime.utcnow()
                db.session.commit()
                self.is_running = True
                
                logger.info(f"Starting simulation: {sim.name} (ID: {self.simulation_id})")
                
                # Emit simulation started event
                socketio.emit('simulation_started', {
                    'simulation_id': self.simulation_id,
                    'status': 'running',
                    'message': 'Simulation started successfully'
                })
                
                # Start interaction loop
                self.greenthread = eventlet.spawn(self._interaction_loop)
            
        except ValueError as e:
            logger.error(f"Validation error starting simulation: {str(e)}")
            self._handle_simulation_error(str(e))
        except SQLAlchemyError as e:
            logger.error(f"Database error starting simulation: {str(e)}")
            self._handle_simulation_error("Database error occurred")
        except Exception as e:
            logger.error(f"Unexpected error starting simulation: {str(e)}")
            self._handle_simulation_error("Unexpected error occurred")
    
    def _generate_interaction_context(self, initiator, receiver):
        """Generate context for interaction based on scenario and custom context."""
        with app.app_context():
            # Refresh simulation object to ensure it's bound to session
            self.simulation = db.session.merge(self.simulation)
            scenario = self.simulation.scenario
            
            if not scenario:
                base_context = f"Current simulation: {self.simulation.name}"
            else:
                base_context = f"Scenario: {scenario.name}\n{scenario.context}\n"
                
            # Add custom context if available
            if self.custom_context:
                base_context = f"{base_context}\nCustom Context:\n{self.custom_context}"
                
            return f"{base_context}\nCurrent simulation: {self.simulation.name}"
    
    def _interaction_loop(self):
        """Main interaction loop with retry mechanism and error handling."""
        while self.is_running:
            try:
                with app.app_context():
                    # Reset error count on successful iteration
                    if self.error_count > 0:
                        self.error_count = 0
                    
                    # Get selected personas
                    selected_personas = (
                        Persona.query.filter(Persona.id.in_(self.selected_persona_ids)).all()
                        if self.selected_persona_ids
                        else Persona.query.all()
                    )
                    
                    if len(selected_personas) < 2:
                        raise ValueError("Insufficient personas for interaction")
                    
                    # Choose random pair from selected personas
                    initiator, receiver = random.sample(selected_personas, 2)
                    
                    # Generate interaction context
                    context = self._generate_interaction_context(initiator, receiver)
                    
                    # Generate interaction with retries
                    self._generate_interaction_with_retry(initiator, receiver, context)
                    
                # Add delay between interactions
                eventlet.sleep(10)
                
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in interaction loop (attempt {self.error_count}): {str(e)}")
                
                if self.error_count >= self.max_errors:
                    logger.error("Maximum error count reached, stopping simulation")
                    self.end_simulation("Maximum error count reached")
                    break
                
                socketio.emit('simulation_warning', {
                    'simulation_id': self.simulation_id,
                    'message': f'Error generating interaction (attempt {self.error_count})'
                })
                eventlet.sleep(self.RETRY_DELAY)
    
    def _generate_interaction_with_retry(self, initiator, receiver, context, retry_count=0):
        """Generate interaction with retry mechanism."""
        try:
            with app.app_context():
                # Refresh simulation object
                self.simulation = db.session.merge(self.simulation)
                
                # Emit status update
                socketio.emit('generating_interaction', {
                    'simulation_id': self.simulation_id,
                    'initiator': initiator.name,
                    'receiver': receiver.name
                })
                
                interaction_data = generate_interaction(initiator, receiver, context)
                
                # Create and save interaction
                interaction = Interaction()
                interaction.simulation_id = self.simulation_id
                interaction.initiator_id = initiator.id
                interaction.receiver_id = receiver.id
                interaction.content = str(interaction_data['dialogue'])
                
                db.session.add(interaction)
                db.session.commit()
                
                # Emit new interaction event
                socketio.emit('new_interaction', {
                    'simulation_id': self.simulation_id,
                    'interaction': {
                        'initiator': initiator.name,
                        'receiver': receiver.name,
                        'content': interaction_data['dialogue'],
                        'timestamp': interaction.timestamp.isoformat(),
                        'sentiment': interaction_data.get('sentiment', 'neutral')
                    }
                })
            
        except Exception as e:
            logger.error(f"Error generating interaction (attempt {retry_count + 1}): {str(e)}")
            if retry_count < self.MAX_RETRIES:
                eventlet.sleep(self.RETRY_DELAY)
                return self._generate_interaction_with_retry(initiator, receiver, context, retry_count + 1)
            raise
    
    def _handle_simulation_error(self, error_message):
        """Handle simulation errors consistently."""
        self.is_running = False
        if self.greenthread:
            self.greenthread.kill()
        
        try:
            with app.app_context():
                if not self.simulation:
                    self._load_simulation()
                
                sim = self.simulation
                sim.status = 'error'
                db.session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error updating simulation status: {str(e)}")
        
        socketio.emit('simulation_error', {
            'simulation_id': self.simulation_id,
            'error': error_message
        })
    
    def end_simulation(self, reason="Simulation completed"):
        """End simulation with proper cleanup."""
        try:
            self.is_running = False
            if self.greenthread:
                self.greenthread.kill()
            
            with app.app_context():
                if not self.simulation:
                    self._load_simulation()
                    
                sim = self.simulation
                sim.status = 'completed'
                sim.end_time = datetime.utcnow()
                db.session.commit()
                
                logger.info(f"Ending simulation {self.simulation_id}: {reason}")
                
                socketio.emit('simulation_ended', {
                    'simulation_id': self.simulation_id,
                    'status': 'completed',
                    'message': reason
                })
            
        except SQLAlchemyError as e:
            logger.error(f"Database error ending simulation: {str(e)}")
            self._handle_simulation_error("Error ending simulation")
        except Exception as e:
            logger.error(f"Unexpected error ending simulation: {str(e)}")
            self._handle_simulation_error("Unexpected error ending simulation")
