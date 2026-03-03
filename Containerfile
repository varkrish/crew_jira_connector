FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /app

# Standalone repo: build context is repo root (.)
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && pip install -e .

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "crew_jira_connector.app:app", "--host", "0.0.0.0", "--port", "8080"]
