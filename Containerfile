FROM registry.access.redhat.com/ubi9/python-312:latest

WORKDIR /app

# Copy into /tmp; re-copy into writable /tmp/build so setuptools can write egg-info (rootless/non-root fix)
COPY . /tmp/pkg
RUN mkdir -p /tmp/build && cp -r /tmp/pkg/. /tmp/build/ \
    && pip install --no-cache-dir -r /tmp/build/requirements.txt && pip install /tmp/build
WORKDIR /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "crew_jira_connector.app:app", "--host", "0.0.0.0", "--port", "8080"]
