FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /app

# Build from repo root: docker build -f crew_jira_connector/Containerfile .
COPY crew_jira_connector/ crew_jira_connector/
RUN pip install --no-cache-dir -r crew_jira_connector/requirements.txt && \
    pip install -e crew_jira_connector/

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "crew_jira_connector.app:app", "--host", "0.0.0.0", "--port", "8080"]
