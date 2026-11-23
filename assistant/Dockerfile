# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py providers.py ./
COPY web ./web
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--threads", "8", "--timeout", "150", "app:app"]
