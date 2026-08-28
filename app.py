import os
import logging
from backend import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize the Flask application using the factory
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1")
    logger.info(f"🚀 Any Help server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
