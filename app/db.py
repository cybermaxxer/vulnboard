import mysql.connector                         # Official MySQL driver for Python
from flask import current_app, g               # current_app reads Config settings; g stores objects for the current request

def get_db():                                  # Function to open or retrieve an active database connection, it will be executed when the app needs to interact with the database
    if 'db' not in g:                          # Checks if a database connection has not been opened yet for this request
        g.db = mysql.connector.connect(        # Opens a new connection pipeline to the MySQL database
            host=current_app.config['MYSQL_HOST'],      # Reads database host ('db') from Config
            user=current_app.config['MYSQL_USER'],      # Reads database user from Config
            password=current_app.config['MYSQL_PASSWORD'], # Reads database password from Config
            database=current_app.config['MYSQL_DB']     # Reads database schema name from Config
        )
    return g.db                                # Returns the open connection stored in g.db

def close_db(e=None):                          # Function that cleans up the database connection after a request finishes
    db = g.pop('db', None)                     # Removes the database connection from g storage
    if db is not None:                         # If an active connection existed...
        db.close()                             # Closes the connection to free server resources