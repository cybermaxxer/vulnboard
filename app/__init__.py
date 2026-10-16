#a filename __init__.py this basically means that whenever anybody imports the app package, this file will be executed automatically. It is used to initialize the package and set up any necessary configurations or dependencies.
#it also contains the application factory function create_app() that builds and returns a Flask app instance. This is a common pattern in Flask applications to allow for flexible configuration and testing.
#also the thing about __init__.py is that it can be empty, but it must be present in the directory to indicate that the directory should be treated as a package. In this case, it contains code to set up the Flask app and its configuration.

from flask import Flask                        # Imports main Flask web framework class
from app.config import Config                  # Imports Config class created in Step 1
from app.db import close_db                    # Imports close_db cleanup function created in Step 2

def create_app():                              # Application Factory function that builds and returns the Flask app
    app = Flask(__name__)                      # Instantiates Flask using current module name. it is equal to app = Flask("app") because the folder name is "app" in this case.
    app.config.from_object(Config)             # Loads all attributes from Config class into Flask's internal config dictionary
    app.teardown_appcontext(close_db)          # Registers close_db to run automatically at end of every HTTP request

    @app.route("/")                            # Route Decorator: maps URL path '/' to index() function below
    def index():
        return "VulnBoard setup complete and running!" # Text sent back to user browser on visiting http://127.0.0.1:5000/

    @app.route("/debug-test")                  # Route Decorator: maps URL path '/debug-test' to debug_test() function
    def debug_test():
        raise RuntimeError("Testing stack trace output in debug mode") # Forces app crash to test Werkzeug debug output

    return app                                 # Returns the fully configured Flask app instance