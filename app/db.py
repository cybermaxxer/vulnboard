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
        g.pop('cursor', None)
        
def get_username_by_id(user_id):
    if user_id is None:
        return None
    db = get_db()  # Retrieves the active database connection using the get_db() function, g.db
    cursor = db.cursor(dictionary=True)  # Creates a new cursor object to execute SQL queries
    sql_query = f"SELECT username FROM users WHERE id = {user_id}"  # SQL query to retrieve the username based on the user ID
    cursor.execute(sql_query)  # Executes the SQL query
    user = cursor.fetchone()  # Fetches the first row of the result set as a dictionary
    cursor.close()  # Closes the cursor to free up database resources
    if user is not None:  # If a user record was found in the database
        return user["username"]  # Returns the username associated with the provided user ID
    return None  # Returns None if no user record was found for the provided user ID