import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_socketio import SocketIO
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, desc, case, or_
from logging.handlers import RotatingFileHandler
import json
from scenarios_data import PREDEFINED_SCENARIOS
from database import db

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
logger.addHandler(handler)

# Initialize SocketIO with proper configuration
socketio = SocketIO(
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1000,
    reconnection_delay_max=5000
)

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
    
    # Use the DATABASE_URL from environment
    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['DEBUG'] = True  # Enable debug mode
    
    # Initialize extensions
    db.init_app(app)
    socketio.init_app(app, async_mode='eventlet')
    
    return app

app = create_app()
logger.info('Application instance created')

# Import models after creating db instance
from models import Persona, Simulation, Interaction, Scenario

class ModelEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, (Simulation, Interaction, Persona, Scenario)):
            return {k: v for k, v in o.__dict__.items() if not k.startswith('_')}
        return super().default(o)

app.json_encoder = ModelEncoder

def init_db():
    try:
        with app.app_context():
            db.create_all()
            logger.info('Database tables created successfully')
    except SQLAlchemyError as e:
        logger.error(f'Database initialization error: {str(e)}')
        raise

@app.before_request
def before_request():
    logger.info(f'Processing request to {request.endpoint}')

@app.errorhandler(404)
def not_found_error(error):
    logger.error(f'Page not found: {request.url}')
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f'Server Error: {error}')
    return render_template('error.html', error='Internal server error'), 500

@app.route("/")
def index():
    logger.info('Accessing index page')
    return render_template("index.html")

@app.route("/analytics")
def analytics():
    try:
        # Calculate key metrics
        metrics = {
            'total_simulations': Simulation.query.count(),
            'total_personas': Persona.query.count(),
            'total_interactions': Interaction.query.count(),
            'avg_interactions_per_sim': db.session.query(
                func.avg(
                    db.session.query(func.count(Interaction.id))
                    .filter(Interaction.simulation_id == Simulation.id)
                    .group_by(Interaction.simulation_id)
                    .as_scalar()
                )
            ).scalar() or 0,
            'active_simulations': Simulation.query.filter_by(status='running').count(),
            'completed_simulations': Simulation.query.filter_by(status='completed').count()
        }

        # Get timeline data (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        timeline_query = db.session.query(
            func.date_trunc('day', Interaction.timestamp).label('date'),
            func.count(Interaction.id).label('count')
        ).filter(Interaction.timestamp >= thirty_days_ago)\
         .group_by('date')\
         .order_by('date')

        timeline_data = {
            'labels': [],
            'values': []
        }
        
        # Fill in missing dates with zero values
        current_date = thirty_days_ago.date()
        end_date = datetime.utcnow().date()
        date_counts = {result.date.date(): result.count for result in timeline_query}
        
        while current_date <= end_date:
            timeline_data['labels'].append(current_date.strftime('%Y-%m-%d'))
            timeline_data['values'].append(date_counts.get(current_date, 0))
            current_date += timedelta(days=1)

        # Get detailed persona interaction distribution
        persona_distribution = {
            'labels': [],
            'values': [],
            'initiated': [],
            'received': []
        }
        
        top_personas = db.session.query(
            Persona.name,
            func.count(Interaction.id).label('total_interactions'),
            func.count(case([(Interaction.initiator_id == Persona.id, 1)])).label('initiated'),
            func.count(case([(Interaction.receiver_id == Persona.id, 1)])).label('received')
        ).outerjoin(
            Interaction, 
            or_(Persona.id == Interaction.initiator_id, Persona.id == Interaction.receiver_id)
        ).group_by(Persona.id)\
         .order_by(desc('total_interactions'))\
         .limit(10)

        for persona in top_personas:
            persona_distribution['labels'].append(persona.name)
            persona_distribution['values'].append(persona.total_interactions)
            persona_distribution['initiated'].append(persona.initiated)
            persona_distribution['received'].append(persona.received)

        # Get personality traits distribution with trend analysis
        traits_data = {
            'behavior_patterns': {},
            'interaction_styles': {},
            'emotional_ranges': {},
            'communication_preferences': {}
        }
        
        for field in ['behavior_pattern', 'interaction_style', 'emotional_range', 'communication_preference']:
            query = db.session.query(
                getattr(Persona, field),
                func.count(Persona.id).label('count'),
                func.count(Interaction.id).label('interaction_count')
            ).outerjoin(
                Interaction, 
                or_(Persona.id == Interaction.initiator_id, Persona.id == Interaction.receiver_id)
            ).group_by(getattr(Persona, field))
            
            results = query.all()
            traits_data[field + 's'] = {
                'labels': [r[0] for r in results if r[0]],
                'counts': [r[1] for r in results if r[0]],
                'interaction_counts': [r[2] for r in results if r[0]]
            }

        # Get recent activities with more context
        recent_activities = db.session.query(
            Interaction.timestamp,
            Simulation.name.label('simulation_name'),
            Persona.name.label('initiator_name'),
            Interaction.content.label('description')
        ).join(Simulation)\
         .join(Persona, Interaction.initiator_id == Persona.id)\
         .order_by(desc(Interaction.timestamp))\
         .limit(10)

        # Generate hourly activity heatmap data
        heatmap_data = db.session.query(
            func.extract('hour', Interaction.timestamp).label('hour'),
            func.count(Interaction.id).label('count')
        ).group_by('hour')\
         .order_by('hour')\
         .all()
        
        hourly_activity = {
            'labels': list(range(24)),
            'values': [0] * 24
        }
        
        for hour, count in heatmap_data:
            if hour is not None:
                hourly_activity['values'][int(hour)] = count

        return render_template(
            "analytics.html",
            metrics=metrics,
            timeline_data=timeline_data,
            persona_distribution=persona_distribution,
            traits_data=traits_data,
            recent_activities=recent_activities,
            hourly_activity=hourly_activity
        )
    except SQLAlchemyError as e:
        logger.error(f'Database error in analytics route: {str(e)}')
        flash("Error loading analytics data.", "error")
        return redirect(url_for("index"))

@app.route("/personas", methods=["GET", "POST"])
def personas():
    if request.method == "POST":
        try:
            persona = Persona(
                name=request.form.get("name"),
                avatar=request.form.get("avatar"),
                personality=request.form.get("personality"),
                interests=request.form.get("interests"),
                goals=request.form.get("goals"),
                behavior_pattern=request.form.get("behavior_pattern"),
                interaction_style=request.form.get("interaction_style"),
                emotional_range=request.form.get("emotional_range"),
                communication_preference=request.form.get("communication_preference"),
                tags=request.form.get("tags")
            )
            
            db.session.add(persona)
            db.session.commit()
            logger.info(f'Created new persona: {persona.name}')
            flash("Persona created successfully!", "success")
            return redirect(url_for("personas"))
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f'Database error while creating persona: {str(e)}')
            flash("Error creating persona. Please try again.", "error")
            return redirect(url_for("personas"))
    
    personas = Persona.query.all()
    return render_template("personas.html", personas=personas)

@app.route("/simulation")
def simulation():
    try:
        personas = Persona.query.all()
        scenarios = Scenario.query.all()
        
        # Initialize scenarios if none exist
        if not scenarios:
            for scenario_data in PREDEFINED_SCENARIOS:
                scenario = Scenario(**scenario_data)
                db.session.add(scenario)
            db.session.commit()
            scenarios = Scenario.query.all()
            
        return render_template(
            "simulation.html",
            personas=personas,
            scenarios=scenarios
        )
    except SQLAlchemyError as e:
        logger.error(f'Database error in simulation route: {str(e)}')
        flash("Error loading simulation data.", "error")
        return redirect(url_for("index"))

@app.route("/simulation/start", methods=["POST"])
def start_simulation():
    from simulation_manager import SimulationManager
    try:
        data = request.get_json()
        name = data.get("name")
        scenario_id = data.get("scenario_id")
        persona_ids = data.get("personas")
        custom_context = data.get("custom_context")
        conversation_depth = data.get("conversation_depth", "medium")
        
        # Validate required fields
        if not all([name, scenario_id, persona_ids]) or len(persona_ids) < 2:
            logger.warning('Invalid simulation start request')
            return jsonify({"error": "Invalid request data"}), 400
        
        # Validate conversation depth
        valid_depths = ['short', 'medium', 'long', 'extended', 'longform', 'marathon']
        if conversation_depth not in valid_depths:
            logger.warning(f'Invalid conversation depth: {conversation_depth}')
            return jsonify({"error": "Invalid conversation depth"}), 400
            
        # Validate scenario requirements
        scenario = Scenario.query.get(scenario_id)
        if not scenario:
            return jsonify({"error": "Invalid scenario"}), 400
            
        if len(persona_ids) < scenario.min_participants or \
           (scenario.max_participants and len(persona_ids) > scenario.max_participants):
            return jsonify({"error": "Invalid number of participants for selected scenario"}), 400
            
        simulation = Simulation(
            name=name,
            status="pending",
            scenario_id=scenario_id,
            description=f"Custom simulation with context: {custom_context[:100]}..." if custom_context else None
        )
        db.session.add(simulation)
        db.session.commit()
        
        # Pass validated conversation depth to SimulationManager
        manager = SimulationManager(
            simulation.id,
            persona_ids=persona_ids,
            socketio=socketio,
            app=app,
            conversation_depth=conversation_depth
        )
        
        # Pass custom context to the simulation manager
        manager.custom_context = custom_context
        manager.start_simulation()
        
        logger.info(f'Started simulation: {name} with scenario: {scenario.name} '
                   f'and depth: {conversation_depth}')
        
        return jsonify({"simulation_id": simulation.id}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error starting simulation: {str(e)}')
        return jsonify({"error": str(e)}), 500

@app.route("/simulation/<int:id>/stop", methods=["POST"])
def stop_simulation(id):
    from simulation_manager import SimulationManager
    try:
        manager = SimulationManager(id, socketio=socketio, app=app)
        manager.end_simulation()
        logger.info(f'Stopped simulation: {id}')
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f'Error stopping simulation: {str(e)}')
        return jsonify({"error": str(e)}), 500

@app.route("/results")
def results():
    try:
        # Get all simulations with their related data
        simulations = (
            Simulation.query
            .options(db.joinedload(Simulation.interactions)
                    .joinedload(Interaction.initiator))
            .options(db.joinedload(Simulation.interactions)
                    .joinedload(Interaction.receiver))
            .all()
        )
        
        # Prepare serializable data for the template with enhanced analytics
        serializable_simulations = []
        for simulation in simulations:
            sim_data = {
                'id': simulation.id,
                'name': simulation.name,
                'start_time': simulation.start_time,
                'end_time': simulation.end_time,
                'status': simulation.status,
                'interactions': [],
                'analytics': {
                    'total_interactions': len(simulation.interactions),
                    'resolution_stats': {'resolved': 0, 'partially_resolved': 0, 'unresolved': 0},
                    'relationship_impact': {'strengthened': 0, 'unchanged': 0, 'strained': 0},
                    'avg_metrics': {
                        'interaction_quality': 0,
                        'communication_effectiveness': 0,
                        'conflict_intensity': 0,
                        'resolution_quality': 0
                    },
                    'key_points': set(),
                    'tension_points': set()
                }
            }
            
            # Process interactions and collect analytics
            quality_scores = []
            comm_scores = []
            conflict_scores = []
            resolution_scores = []
            
            for interaction in sorted(simulation.interactions, key=lambda x: x.timestamp):
                int_data = {
                    'timestamp': interaction.timestamp,
                    'initiator': {'name': interaction.initiator.name},
                    'receiver': {'name': interaction.receiver.name},
                    'content': interaction.content,
                    'metadata': interaction.interaction_metadata
                }
                
                sim_data['interactions'].append(int_data)
                
                # Aggregate analytics from metadata
                if interaction.interaction_metadata:
                    metadata = interaction.interaction_metadata
                    
                    # Resolution status
                    status = metadata.get('outcome', {}).get('resolution_status')
                    if status in sim_data['analytics']['resolution_stats']:
                        sim_data['analytics']['resolution_stats'][status] += 1
                    
                    # Relationship impact
                    impact = metadata.get('outcome', {}).get('relationship_impact')
                    if impact in sim_data['analytics']['relationship_impact']:
                        sim_data['analytics']['relationship_impact'][impact] += 1
                    
                    # Key points and tension points
                    sim_data['analytics']['key_points'].update(
                        metadata.get('outcome', {}).get('key_points', [])
                    )
                    sim_data['analytics']['tension_points'].update(
                        metadata.get('outcome', {}).get('tension_points', [])
                    )
                    
                    # Collect scores for averaging
                    if 'analysis' in metadata:
                        analysis = metadata['analysis']
                        if 'interaction_quality' in analysis:
                            quality_scores.append(float(analysis['interaction_quality']))
                        if 'communication_effectiveness' in analysis:
                            comm_scores.append(float(analysis['communication_effectiveness']))
                        if 'conflict_intensity' in analysis:
                            conflict_scores.append(float(analysis['conflict_intensity']))
                        if 'resolution_quality' in analysis:
                            resolution_scores.append(float(analysis['resolution_quality']))
            
            # Calculate averages
            if quality_scores:
                sim_data['analytics']['avg_metrics']['interaction_quality'] = sum(quality_scores) / len(quality_scores)
            if comm_scores:
                sim_data['analytics']['avg_metrics']['communication_effectiveness'] = sum(comm_scores) / len(comm_scores)
            if conflict_scores:
                sim_data['analytics']['avg_metrics']['conflict_intensity'] = sum(conflict_scores) / len(conflict_scores)
            if resolution_scores:
                sim_data['analytics']['avg_metrics']['resolution_quality'] = sum(resolution_scores) / len(resolution_scores)
            
            # Convert sets to lists for JSON serialization
            sim_data['analytics']['key_points'] = list(sim_data['analytics']['key_points'])
            sim_data['analytics']['tension_points'] = list(sim_data['analytics']['tension_points'])
            
            serializable_simulations.append(sim_data)
        
        return render_template("results.html", simulations=serializable_simulations)
    except SQLAlchemyError as e:
        logger.error(f'Database error in results route: {str(e)}')
        flash("Error loading results.", "error")
        return redirect(url_for("index"))

@app.route("/scenarios", methods=["GET", "POST"])
def scenarios():
    try:
        if request.method == "POST":
            data = request.get_json()
            scenario = Scenario(
                name=data['name'],
                description=data['description'],
                context=data['context'],
                category=data['category'],
                difficulty=data['difficulty'],
                min_participants=int(data['min_participants']),
                max_participants=int(data['max_participants']),
                duration_minutes=int(data['duration_minutes'])
            )
            db.session.add(scenario)
            db.session.commit()
            return jsonify({"success": True, "scenario_id": scenario.id})
        
        scenarios = Scenario.query.order_by(Scenario.category, Scenario.name).all()
        return render_template("scenarios.html", scenarios=scenarios)
    except SQLAlchemyError as e:
        logger.error(f'Database error in scenarios route: {str(e)}')
        if request.method == "POST":
            return jsonify({"success": False, "error": "Database error"}), 500
        flash("Error loading scenarios.", "error")
        return redirect(url_for("index"))

@app.route("/scenarios/create", methods=["POST"])
def create_scenario():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'description', 'context', 'category', 'difficulty', 
                         'min_participants', 'max_participants', 'duration_minutes']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        # Validate field types and ranges
        try:
            min_participants = int(data['min_participants'])
            max_participants = int(data['max_participants'])
            duration_minutes = int(data['duration_minutes'])
            
            if min_participants < 2:
                return jsonify({
                    "success": False,
                    "error": "Minimum participants must be at least 2"
                }), 400
                
            if max_participants < min_participants:
                return jsonify({
                    "success": False,
                    "error": "Maximum participants must be greater than or equal to minimum participants"
                }), 400
                
            if duration_minutes < 15:
                return jsonify({
                    "success": False,
                    "error": "Duration must be at least 15 minutes"
                }), 400
        except ValueError:
            return jsonify({
                "success": False,
                "error": "Invalid numeric values provided"
            }), 400
        
        # Validate category and difficulty
        valid_categories = ["Professional", "Service", "Technical", "Healthcare", 
                          "Education", "Research", "Management", "Creative"]
        valid_difficulties = ["Easy", "Medium", "Hard"]
        
        if data['category'] not in valid_categories:
            return jsonify({
                "success": False,
                "error": f"Invalid category. Must be one of: {', '.join(valid_categories)}"
            }), 400
            
        if data['difficulty'] not in valid_difficulties:
            return jsonify({
                "success": False,
                "error": f"Invalid difficulty. Must be one of: {', '.join(valid_difficulties)}"
            }), 400
        
        # Create scenario
        scenario = Scenario(
            name=data['name'],
            description=data['description'],
            context=data['context'],
            category=data['category'],
            difficulty=data['difficulty'],
            min_participants=min_participants,
            max_participants=max_participants,
            duration_minutes=duration_minutes
        )
        
        db.session.add(scenario)
        db.session.commit()
        logger.info(f'Created new scenario: {scenario.name}')
        
        return jsonify({
            "success": True,
            "scenario_id": scenario.id,
            "message": "Scenario created successfully"
        })
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Database error creating scenario: {str(e)}')
        return jsonify({
            "success": False,
            "error": "Database error occurred while creating scenario"
        }), 500
    except Exception as e:
        logger.error(f'Error creating scenario: {str(e)}')
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)