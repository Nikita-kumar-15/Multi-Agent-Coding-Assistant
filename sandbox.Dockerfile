FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask requests pytest
