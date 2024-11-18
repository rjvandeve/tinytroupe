import random
from datetime import datetime
import eventlet
from database import db
from models import Simulation, Interaction, Persona
from chat_request import generate_interaction
from sqlalchemy.exc import SQLAlchemyError
import time
import logging
from flask import current_app
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

class SimulationManager:
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    
    # Define depth ranges
    DEPTH_RANGES = {
        'short': (1, 2),
        'medium': (3, 5),
        'long': (6, 10),
        'extended': (11, 25),
        'longform': (26, 50),
        'marathon': (51, 100)
    }
    
    def __init__(self, simulation_id, persona_ids=None, socketio=None, app=None, conversation_depth='medium'):
        self.simulation_id = simulation_id
        self.is_running = False
        self.greenthread = None
        self.error_count = 0
        self.max_errors = 5
        self.simulation = None
        self.custom_context = None
        self.selected_persona_ids = persona_ids or []
        self.socketio = socketio or SocketIO()
        self.app = app or current_app
        self.conversation_pairs = {}  # Track ongoing conversations
        self.completed_pairs = set()  # Track completed conversation pairs
        
        # Validate and set conversation depth
        if conversation_depth not in self.DEPTH_RANGES:
            logger.warning(f"Invalid conversation depth '{conversation_depth}', defaulting to 'medium'")
            conversation_depth = 'medium'
        self.conversation_depth = conversation_depth
        
        logger.info(f"Initializing simulation with conversation depth: {conversation_depth} "
                   f"(range: {self.DEPTH_RANGES[conversation_depth]})")
        self._load_simulation()

    def _load_simulation(self):
        try:
            with self.app.app_context():
                self.simulation = Simulation.query.get(self.simulation_id)
                if not self.simulation:
                    raise ValueError(f"Simulation {self.simulation_id} not found")
                logger.info(f"Loaded simulation: {self.simulation.name}")
        except Exception as e:
            logger.error(f"Error loading simulation: {str(e)}")
            raise
    
    def _get_max_depth(self):
        """Get maximum conversation depth based on setting with strict validation."""
        depth_range = self.DEPTH_RANGES.get(self.conversation_depth)
        if depth_range is None:
            logger.warning(f"Invalid conversation depth '{self.conversation_depth}', defaulting to medium (3-5)")
            self.conversation_depth = 'medium'
            depth_range = self.DEPTH_RANGES['medium']
        
        max_depth = depth_range[1]
        logger.info(f"Using conversation depth: {self.conversation_depth} "
                   f"(range: {depth_range}, max: {max_depth} exchanges)")
        return max_depth
    
    def _get_min_depth(self):
        """Get minimum conversation depth based on setting."""
        return self.DEPTH_RANGES.get(self.conversation_depth, (3, 5))[0]
    
    def _should_continue_conversation(self, initiator_id, receiver_id):
        """Determine if the current conversation should continue with strict validation."""
        pair_key = tuple(sorted([initiator_id, receiver_id]))
        current_depth = self.conversation_pairs.get(pair_key, 0)
        min_depth = self._get_min_depth()
        max_depth = self._get_max_depth()
        
        # Strict validation: Immediately return False if max depth reached or exceeded
        if current_depth >= max_depth:
            if pair_key not in self.completed_pairs:
                self.completed_pairs.add(pair_key)
                logger.info(f"Conversation pair {pair_key} completed with target depth {max_depth}")
            return False
        
        # Log current conversation status
        logger.info(f"Checking conversation continuation for pair {pair_key}: "
                   f"current depth: {current_depth}, range: {min_depth}-{max_depth}")
        
        # Continue only if below max depth
        remaining = max_depth - current_depth
        logger.info(f"Continuing conversation {pair_key}: {remaining} exchanges remaining")
        return True
    
    def _update_conversation_count(self, initiator_id, receiver_id):
        """Update the conversation count with strict validation and enhanced logging."""
        pair_key = tuple(sorted([initiator_id, receiver_id]))
        max_depth = self._get_max_depth()

        # Prevent incrementing beyond max depth
        if pair_key in self.conversation_pairs:
            current_depth = self.conversation_pairs[pair_key]
            if current_depth >= max_depth:
                logger.warning(f"Attempted to increment conversation {pair_key} beyond max depth {max_depth}")
                return False
            
            # Increment conversation count
            self.conversation_pairs[pair_key] += 1
            current_depth = self.conversation_pairs[pair_key]
            
            # Log progress
            progress_percentage = (current_depth / max_depth) * 100
            logger.info(f"Conversation progress for pair {pair_key}: "
                       f"{current_depth}/{max_depth} exchanges ({progress_percentage:.1f}%)")
            
            # Mark as complete if max depth reached
            if current_depth >= max_depth:
                if pair_key not in self.completed_pairs:
                    self.completed_pairs.add(pair_key)
                    logger.info(f"Conversation pair {pair_key} completed with target depth {max_depth}")
        else:
            # Initialize new conversation
            self.conversation_pairs[pair_key] = 1
            logger.info(f"Started new conversation pair {pair_key} (1/{max_depth} exchanges)")
        
        return True

    def _generate_interaction_with_retry(self, initiator, receiver, context, retry_count=0):
        """Generate interaction with retry mechanism and depth validation."""
        try:
            with self.app.app_context():
                # Validate conversation depth before generating
                pair_key = tuple(sorted([initiator.id, receiver.id]))
                current_depth = self.conversation_pairs.get(pair_key, 0)
                max_depth = self._get_max_depth()
                
                if current_depth >= max_depth:
                    logger.warning(f"Attempted to generate interaction for completed conversation {pair_key}")
                    return None
                
                # Refresh simulation object
                self.simulation = db.session.merge(self.simulation)
                
                # Emit status update with depth information
                self.socketio.emit('generating_interaction', {
                    'simulation_id': self.simulation_id,
                    'initiator': initiator.name,
                    'receiver': receiver.name,
                    'conversation_depth': f"{current_depth + 1}/{max_depth}"
                })
                
                # Generate interaction
                interaction_data = generate_interaction(
                    initiator, 
                    receiver, 
                    context,
                    simulation_id=self.simulation_id
                )
                
                # Create and save interaction with enhanced data
                interaction = Interaction()
                interaction.simulation_id = self.simulation_id
                interaction.initiator_id = initiator.id
                interaction.receiver_id = receiver.id
                interaction.content = str(interaction_data['dialogue'])
                interaction.interaction_metadata = {
                    'outcome': {
                        'resolution_status': interaction_data.get('outcome', {}).get('resolution_status', 'unknown'),
                        'agreement_level': interaction_data.get('outcome', {}).get('agreement_level', 'none'),
                        'key_points': interaction_data.get('outcome', {}).get('key_points', []),
                        'tension_points': interaction_data.get('outcome', {}).get('tension_points', []),
                        'relationship_impact': interaction_data.get('outcome', {}).get('relationship_impact', 'unchanged')
                    },
                    'analysis': {
                        'interaction_quality': interaction_data.get('analysis', {}).get('interaction_quality', '5'),
                        'communication_effectiveness': interaction_data.get('analysis', {}).get('communication_effectiveness', '5'),
                        'conflict_intensity': interaction_data.get('analysis', {}).get('conflict_intensity', '5'),
                        'resolution_quality': interaction_data.get('analysis', {}).get('resolution_quality', '5')
                    },
                    'sentiment': interaction_data.get('sentiment', 'neutral')
                }
                
                db.session.add(interaction)
                db.session.commit()
                
                # Track conversation outcomes and progression
                pair_key = tuple(sorted([initiator.id, receiver.id]))
                if not hasattr(self, 'conversation_outcomes'):
                    self.conversation_outcomes = {}
                
                if pair_key not in self.conversation_outcomes:
                    self.conversation_outcomes[pair_key] = []
                
                outcome_entry = {
                    'depth': self.conversation_pairs.get(pair_key, 0) + 1,
                    'outcome': interaction_data.get('outcome', {}),
                    'analysis': interaction_data.get('analysis', {}),
                    'timestamp': datetime.utcnow()
                }
                
                self.conversation_outcomes[pair_key].append(outcome_entry)
                
                # Calculate aggregate metrics for the conversation
                current_outcomes = self.conversation_outcomes[pair_key]
                aggregate_metrics = {
                    'avg_interaction_quality': sum(float(o['analysis'].get('interaction_quality', 0)) 
                                               for o in current_outcomes) / len(current_outcomes),
                    'avg_communication_effectiveness': sum(float(o['analysis'].get('communication_effectiveness', 0))
                                                      for o in current_outcomes) / len(current_outcomes),
                    'avg_conflict_intensity': sum(float(o['analysis'].get('conflict_intensity', 0))
                                              for o in current_outcomes) / len(current_outcomes),
                    'avg_resolution_quality': sum(float(o['analysis'].get('resolution_quality', 0))
                                              for o in current_outcomes) / len(current_outcomes),
                    'resolution_rate': sum(1 for o in current_outcomes 
                                      if o['outcome'].get('resolution_status') == 'resolved') / len(current_outcomes),
                    'relationship_progression': {
                        'strengthened': sum(1 for o in current_outcomes 
                                        if o['outcome'].get('relationship_impact') == 'strengthened'),
                        'unchanged': sum(1 for o in current_outcomes 
                                    if o['outcome'].get('relationship_impact') == 'unchanged'),
                        'strained': sum(1 for o in current_outcomes 
                                   if o['outcome'].get('relationship_impact') == 'strained')
                    }
                }
                
                # Calculate relationship trend
                relationship_scores = [1 if o['outcome'].get('relationship_impact') == 'strengthened'
                                    else -1 if o['outcome'].get('relationship_impact') == 'strained'
                                    else 0 for o in current_outcomes]
                relationship_trend = sum(relationship_scores)
                
                aggregate_metrics['relationship_trend'] = (
                    'improving' if relationship_trend > 0
                    else 'deteriorating' if relationship_trend < 0
                    else 'stable'
                )
                
                # Emit new interaction event with enhanced data
                self.socketio.emit('new_interaction', {
                    'simulation_id': self.simulation_id,
                    'interaction': {
                        'initiator': initiator.name,
                        'receiver': receiver.name,
                        'content': interaction_data['dialogue'],
                        'timestamp': interaction.timestamp.isoformat(),
                        'sentiment': interaction_data.get('sentiment', 'neutral'),
                        'outcome': interaction_data.get('outcome', {}),
                        'analysis': interaction_data.get('analysis', {}),
                        'conversation_depth': f"{self.conversation_pairs.get(pair_key, 0) + 1}/{self._get_max_depth()}",
                        'aggregate_metrics': aggregate_metrics
                    }
                })
                
                return interaction
            
        except Exception as e:
            logger.error(f"Error generating interaction (attempt {retry_count + 1}): {str(e)}")
            if retry_count < self.MAX_RETRIES:
                eventlet.sleep(self.RETRY_DELAY)
                return self._generate_interaction_with_retry(initiator, receiver, context, retry_count + 1)
            raise

    def _interaction_loop(self):
        """Main interaction loop with enhanced conversation depth tracking and validation."""
        while self.is_running:
            try:
                with self.app.app_context():
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
                    
                    # Log detailed conversation state
                    logger.info(f"Current conversation state - "
                              f"Active: {len(self.conversation_pairs)}, "
                              f"Completed: {len(self.completed_pairs)}, "
                              f"Target depth: {self._get_max_depth()}, "
                              f"Total pairs possible: {len(selected_personas) * (len(selected_personas) - 1) // 2}")
                    
                    # Select conversation pair based on depth settings
                    initiator, receiver = self._select_conversation_pair(selected_personas)
                    
                    # Check if all conversations are complete
                    if initiator is None or receiver is None:
                        logger.info("All conversations have reached their target depth")
                        self.end_simulation("All conversations completed successfully")
                        break
                    
                    # Validate conversation continuation
                    pair_key = tuple(sorted([initiator.id, receiver.id]))
                    if not self._should_continue_conversation(initiator.id, receiver.id):
                        logger.info(f"Skipping completed conversation pair {pair_key}")
                        continue
                    
                    # Generate interaction context
                    context = self._generate_interaction_context(initiator, receiver)
                    
                    # Generate interaction with retries
                    self._generate_interaction_with_retry(initiator, receiver, context)
                    
                    # Update conversation count with validation
                    self._update_conversation_count(initiator.id, receiver.id)
                    
                    # Verify completion state
                    all_pairs = set(tuple(sorted([p1.id, p2.id])) 
                                  for i, p1 in enumerate(selected_personas) 
                                  for p2 in selected_personas[i+1:])
                    
                    if len(self.completed_pairs) == len(all_pairs):
                        logger.info("All conversation pairs have completed their target depth")
                        self.end_simulation("All conversations completed successfully")
                        break
                    
                # Add delay between interactions
                eventlet.sleep(10)
                
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in interaction loop (attempt {self.error_count}): {str(e)}")
                
                if self.error_count >= self.max_errors:
                    logger.error("Maximum error count reached, stopping simulation")
                    self.end_simulation("Maximum error count reached")
                    break
                
                self.socketio.emit('simulation_warning', {
                    'simulation_id': self.simulation_id,
                    'message': f'Error generating interaction (attempt {self.error_count})'
                })
                eventlet.sleep(self.RETRY_DELAY)
    
    def _generate_interaction_with_retry(self, initiator, receiver, context, retry_count=0):
        """Generate interaction with retry mechanism."""
        try:
            with self.app.app_context():
                # Refresh simulation object
                self.simulation = db.session.merge(self.simulation)
                
                # Emit status update
                self.socketio.emit('generating_interaction', {
                    'simulation_id': self.simulation_id,
                    'initiator': initiator.name,
                    'receiver': receiver.name,
                    'conversation_depth': f"{self.conversation_pairs.get(tuple(sorted([initiator.id, receiver.id])), 0) + 1}/{self._get_max_depth()}"
                })
                
                # Pass simulation_id to maintain conversation context
                interaction_data = generate_interaction(
                    initiator, 
                    receiver, 
                    context,
                    simulation_id=self.simulation_id
                )
                
                # Create and save interaction with enhanced data
                interaction = Interaction()
                interaction.simulation_id = self.simulation_id
                interaction.initiator_id = initiator.id
                interaction.receiver_id = receiver.id
                interaction.content = str(interaction_data['dialogue'])
                interaction.interaction_metadata = {
                    'outcome': {
                        'resolution_status': interaction_data.get('outcome', {}).get('resolution_status', 'unknown'),
                        'agreement_level': interaction_data.get('outcome', {}).get('agreement_level', 'none'),
                        'key_points': interaction_data.get('outcome', {}).get('key_points', []),
                        'tension_points': interaction_data.get('outcome', {}).get('tension_points', []),
                        'relationship_impact': interaction_data.get('outcome', {}).get('relationship_impact', 'unchanged')
                    },
                    'analysis': {
                        'interaction_quality': interaction_data.get('analysis', {}).get('interaction_quality', '5'),
                        'communication_effectiveness': interaction_data.get('analysis', {}).get('communication_effectiveness', '5'),
                        'conflict_intensity': interaction_data.get('analysis', {}).get('conflict_intensity', '5'),
                        'resolution_quality': interaction_data.get('analysis', {}).get('resolution_quality', '5')
                    },
                    'sentiment': interaction_data.get('sentiment', 'neutral')
                }
                
                db.session.add(interaction)
                db.session.commit()
                
                # Track conversation outcomes
                pair_key = tuple(sorted([initiator.id, receiver.id]))
                if not hasattr(self, 'conversation_outcomes'):
                    self.conversation_outcomes = {}
                
                if pair_key not in self.conversation_outcomes:
                    self.conversation_outcomes[pair_key] = []
                
                self.conversation_outcomes[pair_key].append({
                    'depth': self.conversation_pairs.get(pair_key, 0) + 1,
                    'outcome': interaction_data.get('outcome', {}),
                    'analysis': interaction_data.get('analysis', {})
                })
                
                # Calculate aggregate metrics for the conversation
                current_outcomes = self.conversation_outcomes[pair_key]
                aggregate_metrics = {
                    'avg_interaction_quality': sum(float(o['analysis'].get('interaction_quality', 0)) 
                                                 for o in current_outcomes) / len(current_outcomes),
                    'positive_interactions': sum(1 for o in current_outcomes 
                                              if o['analysis'].get('relationship_impact') == 'positive'),
                    'resolution_rate': sum(1 for o in current_outcomes 
                                        if o['outcome'].get('resolution_status') == 'resolved') / len(current_outcomes)
                }
                
                # Emit new interaction event with enhanced data
                self.socketio.emit('new_interaction', {
                    'simulation_id': self.simulation_id,
                    'interaction': {
                        'initiator': initiator.name,
                        'receiver': receiver.name,
                        'content': interaction_data['dialogue'],
                        'timestamp': interaction.timestamp.isoformat(),
                        'sentiment': interaction_data.get('sentiment', 'neutral'),
                        'outcome': interaction_data.get('outcome', {}),
                        'analysis': interaction_data.get('analysis', {}),
                        'conversation_depth': f"{self.conversation_pairs.get(pair_key, 0) + 1}/{self._get_max_depth()}",
                        'aggregate_metrics': aggregate_metrics
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
            with self.app.app_context():
                if not self.simulation:
                    self._load_simulation()
                
                sim = self.simulation
                sim.status = 'error'
                db.session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error updating simulation status: {str(e)}")
        
        self.socketio.emit('simulation_error', {
            'simulation_id': self.simulation_id,
            'error': error_message
        })
    
    def end_simulation(self, reason="Simulation completed"):
        """End simulation with proper cleanup."""
        try:
            self.is_running = False
            if self.greenthread:
                self.greenthread.kill()
            
            with self.app.app_context():
                if not self.simulation:
                    self._load_simulation()
                    
                sim = self.simulation
                sim.status = 'completed'
                sim.end_time = datetime.utcnow()
                db.session.commit()
                
                logger.info(f"Ending simulation {self.simulation_id}: {reason}")
                
                self.socketio.emit('simulation_ended', {
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
    
    def validate_personas(self):
        """Validate that enough selected personas exist for simulation."""
        try:
            with self.app.app_context():
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
            
    def start_simulation(self, conversation_depth='medium'):
        """Start the simulation with improved error handling."""
        try:
            # Set conversation depth
            self.conversation_depth = conversation_depth
            
            # Validate simulation state
            if self.is_running:
                raise ValueError("Simulation is already running")
                
            # Validate personas
            self.validate_personas()
            
            with self.app.app_context():
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
                self.socketio.emit('simulation_started', {
                    'simulation_id': self.simulation_id,
                    'status': 'running',
                    'message': 'Simulation started successfully',
                    'conversation_depth': self.conversation_depth
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
        with self.app.app_context():
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

    def _select_conversation_pair(self, personas):
        # Create all possible pairs
        possible_pairs = []
        for i in range(len(personas)):
            for j in range(i + 1, len(personas)):
                pair_key = tuple(sorted([personas[i].id, personas[j].id]))
                if pair_key not in self.completed_pairs:
                    # Prioritize ongoing conversations that haven't reached max depth
                    current_depth = self.conversation_pairs.get(pair_key, 0)
                    max_depth = self._get_max_depth()
                    if current_depth < max_depth:
                        possible_pairs.append((personas[i], personas[j], current_depth))

        if not possible_pairs:
            logger.info("No available conversation pairs found")
            return None, None

        # Sort pairs by current depth (prioritize ongoing conversations)
        possible_pairs.sort(key=lambda x: (-x[2] if x[2] > 0 else float('-inf')))
        initiator, receiver, _ = possible_pairs[0]
        
        logger.info(f"Selected conversation pair: {initiator.name} and {receiver.name}")
        return initiator, receiver