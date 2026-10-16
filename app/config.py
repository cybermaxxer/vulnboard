import os                                      # Python's built-in tool for interacting with the Operating System
from dotenv import load_dotenv                 # Function from 'python-dotenv' library that reads key-value text from .env

load_dotenv()                                  # Reads the .env file in the root directory and loads its values into OS environment

class Config:                                  # Creates a container class named Config to hold all app settings in one place
    SECRET_KEY = os.getenv(                    # Tries to get 'FLASK_SECRET_KEY' from .env
        "FLASK_SECRET_KEY", 
        "default-fallback-key"                 # If 'FLASK_SECRET_KEY' doesn't exist, uses this default text instead
    )
    MYSQL_HOST = os.getenv("MYSQL_HOST", "db") # Hostname where database lives ('db' matches service name in Docker Compose)    
    MYSQL_USER = os.getenv("MYSQL_USER", "vulnuser")     # Database username used to connect
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "vulnpass") # Password for the database user
    MYSQL_DB = os.getenv("MYSQL_DATABASE", "vulnboard")  # Name of the database schema we want to connect to
    
    DEBUG = True                               # Enables Flask Debug Mode so error tracebacks print full details (intentional vuln)