import eventlet
eventlet.monkey_patch()

import signal
import sys
from app import app, socketio, logger
from flask_cors import CORS

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "allow_headers": ["Content-Type"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    }
})

def signal_handler(sig, frame):
    logger.info('Shutting down application...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@app.errorhandler(400)
def bad_request_error(error):
    logger.error(f'Bad request: {error}')
    return {'error': 'Bad request'}, 400

@app.errorhandler(401)
def unauthorized_error(error):
    logger.error(f'Unauthorized access: {error}')
    return {'error': 'Unauthorized'}, 401

@app.errorhandler(403)
def forbidden_error(error):
    logger.error(f'Forbidden access: {error}')
    return {'error': 'Forbidden'}, 403

@app.errorhandler(404)
def not_found_error(error):
    logger.error(f'Resource not found: {error}')
    return {'error': 'Not found'}, 404

@app.errorhandler(500)
def internal_server_error(error):
    logger.error(f'Internal server error: {error}')
    return {'error': 'Internal server error'}, 500

if __name__ == "__main__":
    logger.info('Starting application server...')
    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=True,
            log_output=True,
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        logger.error(f'Failed to start server: {str(e)}')
        sys.exit(1)
