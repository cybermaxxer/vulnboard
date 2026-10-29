#logic to authenticate the user and manage their session, including login, logout, and registration functionalities. It may also include password hashing, token generation, and other security measures to protect user credentials and session data.
from flask import request, session, redirect, url_for, render_template, current_app

from logic.db import get_db

def handle_registration():
    username = request.form.get("username")  # Retrieves the username from the submitted form data
    password = request.form.get("password")  # Retrieves the password from the submitted form data
    if not username or not password:  # Checks if either the username or password is missing
        return "Username and password are required.", 400  # Returns an error message with a 400 Bad Request status code
    does_exist = check_user_exists(username)  # Calls a function to check if the username already exists in the database
    if does_exist:  # If the username already exists
        return "Username already exists.", 400  # Returns an error message with a 400 Bad Request status code
    create_user(username, password)  # Calls a function to create a new user in the database with the provided username and password
    return redirect(url_for("login"))  # Redirects the user to the login page after successful registration

def check_user_exists(username):
    db = get_db() # Retrieves the active database connection using the get_db() function, g.db
    cursor = db.cursor(dictionary=True)
    sql_query = f"SELECT * FROM users WHERE username = '{username}'"  # SQL query to check if the username exists in the 'users' table 
    #intentionally vulnerable to SQL injection, as it directly interpolates the username into the query string without proper sanitization or parameterization. This can allow an attacker to manipulate the SQL query by injecting malicious input through the username field.
    cursor.execute(sql_query)  # Executes the SQL query with the provided username as a parameter to prevent SQL injection
    user = cursor.fetchone()  # Fetches the first row of the result set, which will be None if no user is found
    cursor.close()  # Closes the cursor to free up database resources
    if user is not None:  # If a user record was found in the database
        return True  # Returns True, indicating that the username already exists
    return False  # Returns False, indicating that the username does not exist

def create_user(username, password):
    db = get_db()  # Retrieves the active database connection using the get_db() function, g.db
    if check_user_exists(username):  # Checks if the username already exists in the database
        return "user already exists", 400  # Returns False, indicating that the user creation failed due to an existing username
    
    cursor = db.cursor()  # Creates a new cursor object to execute SQL queries
    sql_query = f"INSERT INTO users (username, password) VALUES ('{username}', '{password}')"  # SQL query to insert a new user into the 'users' table
    cursor.execute(sql_query)  # Executes the SQL query to insert the new user into the database
    db.commit()  # Commits the transaction to save the changes to the database
    created = cursor.rowcount > 0  # Checks if any rows were affected by the insert operation
    cursor.close()  # Closes the cursor to free up database resources
    if created:
        return "user created successfully", 201  # Returns True, indicating that the user was successfully created
    return "user creation failed", 500  # Returns False, indicating that the user creation failed

def get_user_by_credentials(username, password):
    db = get_db()  # retrieves active connection, g.db
    cursor = db.cursor(dictionary=True)
    sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"  # vulnerable: both fields interpolated raw into the WHERE clause
    # one of the payloads:
    #a' OR '1'='1 for the password field, which would make the WHERE clause always true and return the first user in the database.
    # basically does the following: ... AND password = '' (automatic 2 quotes, they are interpreted as a string literal that is emptified, right?)
    #so we inject a' OR '1'='1 
    # the things that were supposed to embrace or query become:
    # (begin embracer)'whatever'(close embracer, injected), OR '1'='1(end embracer, intended to be a close embracer)
    
    cursor.execute(sql_query)
    user = cursor.fetchone()
    cursor.close()
    return user

def handle_login():
    username = request.form.get("username")
    password = request.form.get("password")
    if not username or not password:
        return "Username and password are required.", 400
    user = get_user_by_credentials(username, password)  # auth decision now lives entirely in sql
    if user is None:  # no python side re check of password anymore
        return "Invalid username or password.", 401
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("index"))

def handle_logout():
    session.pop("user_id", None)  # Removes the user's ID from the session, effectively logging them out
    session.pop("username", None)  # Removes the user's username from the session
    return redirect(url_for("index"))  # Redirects the user to the index page after logout

def delete_account():
    user_id = session.get("user_id")  # Retrieves the user's ID from the session
    password = request.args.get("password")  # Retrieves the password from the submitted form data
    if not password:  # If the password is not provided in the form submission
        return "Password is required to delete your account.", 400  # Returns an error message with a 400 Bad Request status code
    if not user_id:  # If the user is not logged in (no user ID in session)
        return "You must be logged in to delete your account.", 401  # Returns an error message with a 401 Unauthorized status code
    if not session.get("username"):  # If the user is not logged in (no username in session)
        return "You must be logged in to delete your account.", 401  # Returns an error message with a 401 Unauthorized status code
    user = get_user_by_credentials(session.get("username"), password)  # Retrieves the user record from the database using the provided username and password
    if user is None:  # If the user record is not found (invalid credentials)
        return "Invalid password. Account deletion failed.", 401  # Returns an error message with a 401 Unauthorized status code
    if user["id"] != user_id:  # If the user ID from the database doesn't match the one in the session
        return "You can only delete your own account.", 403  # Returns an error message with a 403 Forbidden status code
    db = get_db()  # Retrieves the active database connection using the get_db() function, g.db
    cursor = db.cursor()  # Creates a new cursor object to execute SQL queries
    #if there are any posts associated with the user, they will be deleted automatically due to the ON DELETE CASCADE constraint defined in the database schema. This ensures that all related data is cleaned up when a user account is deleted.
    cursor.execute(f"DELETE FROM posts WHERE user_id = {user_id}") #just in case though.
    
    sql_query = f"DELETE FROM users WHERE id = {user_id}"  # SQL query to delete the user from the 'users' table based on their ID
    cursor.execute(sql_query)  # Executes the SQL query to delete the user from the database
    db.commit()  # Commits the transaction to save the changes to the database
    cursor.close()  # Closes the cursor to free up database resources
    session.clear()  # Clears all session data, effectively logging the user out after account deletion
    return redirect(url_for("index"))  # Redirects the user to the index page after account deletion
