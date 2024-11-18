from app import app
from generate_personas import create_diverse_personas

with app.app_context():
    create_diverse_personas(503)  # Create 503 diverse personas as specified in the repository description
