# Dockerfile — one-command self-hosting for the click-anywhere app.
#
# WHY THIS EXISTS: Render (see README "Deploy to the cloud") is the easiest
# zero-setup path, but it's still a specific third-party host with its own
# free-tier quirks (cold starts, sleeping after 15 minutes idle). This
# Dockerfile is the vendor-neutral alternative — it runs identically on
# any machine or cloud that can run a container (your own server, AWS/GCP/
# Azure, a college lab machine, etc.), with no dependency on Render at all.
#
# BUILD:
#   docker build -t quantum-traffic-router .
# RUN:
#   docker run -p 5000:5000 quantum-traffic-router
# then open http://127.0.0.1:5000
#
# This packages only what app.py actually needs at runtime (the live
# click-anywhere app) — it does NOT include Playwright/Chromium (only
# needed for tests/test_layout.py in CI, not for serving the app) or
# osmnx's heavier native dependencies unless you specifically need
# prefetch_street_graphs.py inside the container too.

FROM python:3.11-slim

WORKDIR /app

# System packages some of the Python deps (matplotlib, dwave-samplers)
# need at build/runtime that aren't in the slim base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

# Same production entrypoint the README's Render instructions already use
# (see Procfile) — gunicorn, not the Flask dev server, and a generous
# timeout since a QUBO solve on a larger clustered problem can take a few
# seconds.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --timeout 120"]
