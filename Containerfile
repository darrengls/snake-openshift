# Red Hat Universal Base Image with Python (free, works on OpenShift).
FROM registry.access.redhat.com/ubi9/python-312

# The image already uses a non-root user (1001) and /opt/app-root/src.
# OpenShift runs containers with a random UID in group 0, so files must
# be readable by group 0: that is what --chown=1001:0 is for.
COPY --chown=1001:0 app.py ./
COPY --chown=1001:0 static ./static

ENV PORT=8080 \
    APP_VERSION=1.0.0 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "app.py"]
