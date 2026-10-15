FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run with extended timeout and limited workers to manage quota
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 main:app