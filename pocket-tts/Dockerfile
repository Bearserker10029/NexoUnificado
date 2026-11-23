# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/models OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 \
    && pip install --no-cache-dir pocket-tts==3.3.0 \
    && mkdir /models && chown 10001:10001 /models
COPY app.py .
USER 10001:10001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "5"]
