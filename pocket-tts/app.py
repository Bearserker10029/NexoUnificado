# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import io
import os
from contextlib import asynccontextmanager
from threading import Lock

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Response
from pocket_tts import TTSModel
from pydantic import BaseModel, Field
from scipy.io import wavfile

inference = Lock()


@asynccontextmanager
async def lifespan(app):
    torch.set_num_threads(int(os.environ.get('TTS_THREADS', '2')))
    model = TTSModel.load_model(language="spanish")
    app.state.model = model
    app.state.voice = model.get_state_for_audio_prompt("lola")
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/speech")
def speech(payload: Speech):
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Se requiere texto")
    # Las frases llegan en paralelo: se encolan en vez de rechazarlas.
    if not inference.acquire(timeout=120):
        raise HTTPException(503, "La voz está ocupada")
    try:
        model = app.state.model
        samples = model.generate_audio(app.state.voice, text).cpu().numpy()
    finally:
        inference.release()
    audio = io.BytesIO()
    wavfile.write(audio, model.sample_rate, (np.clip(samples, -1, 1) * 32767).astype(np.int16))
    return Response(audio.getvalue(), media_type="audio/wav")
