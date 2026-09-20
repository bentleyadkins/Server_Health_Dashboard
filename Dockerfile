# Use python 3.12..10-slim for light-application version of python
FROM python:3.12.10-slim

# Use the main directory to pull files
WORKDIR /server_health_dashboard

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copies the takes the requirements
COPY requirements.txt .

# Installs required python packages without cache directory
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code after the application has been installed
COPY . .

# Expose FastAPI on port 8000
EXPOSE 8000

# NOTE** Removed --reload to boost cpu and ram performance of the application
# Run Uvicorn listening on all network interfaces (0.0.0.0)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]