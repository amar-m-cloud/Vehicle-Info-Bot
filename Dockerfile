FROM python:3.11-slim

# Install Chromium + its matching driver from Debian repos (version-matched automatically)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* /root/.cache

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code (never copy .env — credentials come from platform env vars)
COPY . .
RUN rm -f .env

# Tell our code where Chrome/chromedriver live
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

CMD ["python", "main.py"]