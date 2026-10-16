# Start with minimal official Linux image pre-configured with Python 3.11
FROM python:3.11-slim

# Set working directory inside container to /app
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy remaining application code into container
COPY . .

# Document that container listens on port 5000 internally
EXPOSE 5000

# Run Flask app on container startup
CMD ["flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5000"]