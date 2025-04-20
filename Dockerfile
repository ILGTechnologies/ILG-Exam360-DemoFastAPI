FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    gcc \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Run FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]