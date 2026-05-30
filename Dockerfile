FROM python:3.14-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage — lean final image
FROM python:3.14-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Ensure state/ and articles/ directories exist (they will be created at runtime,
# but pre-creating avoids permission issues in some environments)
RUN mkdir -p state articles

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "main.py"]
