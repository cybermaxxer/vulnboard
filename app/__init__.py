#a filename __init__.py this basically means that whenever anybody imports the app package, this file will be executed automatically. It is used to initialize the package and set up any necessary configurations or dependencies.
#it also contains the application factory function create_app() that builds and returns a Flask app instance. This is a common pattern in Flask applications to allow for flexible configuration and testing.
#also the thing about __init__.py is that it can be empty, but it must be present in the directory to indicate that the directory should be treated as a package. In this case, it contains code to set up the Flask app and its configuration.

from flask import Flask, render_template, request, redirect, url_for, session, current_app                     # Imports main Flask web framework class
from app.config import *                # Imports Config class created in Step 1
from app.db import *                # Imports close_db cleanup function created in Step 2
from app.auth import *                # Imports handle_registration function created in Step 3
def create_app():                              # Application Factory function that builds and returns the Flask app
    app = Flask(__name__)                      # Instantiates Flask using current module name. it is equal to app = Flask("app") because the folder name is "app" in this case.
    app.config.from_object(Config)             # Loads all attributes from Config class into Flask's internal config dictionary
    app.teardown_appcontext(close_db)          # Registers close_db to run automatically at end of every HTTP request
   # the decorator is something that runs before the function it decorates. In this case, it tells Flask to call the index() function whenever a user visits the root URL of the web application
    # the decorator runs when the app is initialized, not when the function is called. It sets up the routing so that Flask knows which function to call for a given URL path.
    # to make it run or to create something that runs when the function is called, you would need to put that code inside the function itself, not in the decorator, a wrapper function can be used to modify the behavior of the decorated function, but it would still be executed when the decorated function is called, not when the decorator is applied.
    @app.route("/")                             
    def index():
        return render_template("index.html") 
    
    @app.route("/login")                 
    def login():
        return render_template("login.html")  # Renders the login template

    @app.route("/register")                 
    def register():
        return render_template("register.html")  # Renders the registration template

    @app.route("/register", methods=["POST"])
    def register_post():
        return handle_registration()  # Calls the registration handler function from auth.py

    @app.route("/login", methods=["POST"])
    def login_post():
        return handle_login()  # Calls the login handler function from auth.py
    @app.route("/logout")
    def logout():
        session.clear()  # Clears the session data to log the user out
        return redirect(url_for("index"))  # Redirects the user to the index page after logout
    @app.route("/delete")
    def delete():
        return render_template("delete.html")  # Renders the delete account template
    
    @app.route("/delete", methods=["POST"])
    def delete_post():
        return delete_account()  # Calls the delete account handler function from auth.py
    
    @app.route("/users")
    def view_users():
        db = get_db()  # Retrieves the active database connection using the get_db() function, g.db
        cursor = db.cursor(dictionary=True)  # Creates a new cursor object to execute SQL queries
        cursor.execute("SELECT id, username, password FROM users")  # Executes a SQL query to retrieve all usernames and passwords from the 'users' table
        users = cursor.fetchall()  # Fetches all rows of the result set as a list of dictionaries
        cursor.close()  # Closes the cursor to free up database resources
        return render_template("users.html", users=users)  # Renders the view_users template and passes the list of users to it
    
    return app                                 # Returns the fully configured Flask app instance