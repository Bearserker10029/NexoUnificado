// SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
// SPDX-License-Identifier: Apache-2.0
const form = document.querySelector("#composer");

if (form) {
  const chat = document.querySelector("#chat");
  const question = document.querySelector("#question");
  const send = document.querySelector("#send");
  const status = document.querySelector("#status");
  const autoplay = document.querySelector("#autoplay");
  const endpoint = "/airi/api/" + encodeURIComponent(document.body.dataset.tenant);
  let history = [];

  async function post(path, body) {
    const response = await fetch(endpoint + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || "El asistente no pudo completar la solicitud.");
    }
    return response;
  }

  function addMessage(role, text) {
    const message = document.createElement("article");
    message.className = "message " + role;
    const name = document.createElement("strong");
    name.textContent = role === "user" ? "Tú" : "Asistente IA";
    const body = document.createElement("p");
    body.textContent = text;
    message.append(name, body);
    chat.append(message);
    return message;
  }

  function addSpeech(message, answer) {
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "Escuchar respuesta";
    const audioStatus = document.createElement("p");
    audioStatus.setAttribute("role", "status");
    audioStatus.hidden = true;
    message.append(play, audioStatus);

    async function loadAudio() {
      play.disabled = true;
      play.textContent = "Generando audio…";
      audioStatus.hidden = true;
      try {
        const response = await post("/speech", { text: answer.text, ticket: answer.speech_ticket });
        const audio = document.createElement("audio");
        audio.controls = true;
        const source = URL.createObjectURL(await response.blob());
        audio.src = source;
        window.addEventListener("pagehide", (event) => {
          if (!event.persisted) URL.revokeObjectURL(source);
        });
        play.replaceWith(audio);
        await audio.play().catch(() => {
          audioStatus.textContent = "Pulsa reproducir en el control de audio.";
          audioStatus.hidden = false;
        });
      } catch (error) {
        audioStatus.textContent = error.message;
        audioStatus.hidden = false;
      } finally {
        play.disabled = false;
        play.textContent = "Escuchar respuesta";
      }
    }

    play.addEventListener("click", loadAudio);
    if (autoplay.checked) void loadAudio();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = question.value.trim();
    if (!text) return;
    send.disabled = question.disabled = true;
    status.textContent = "Esperando respuesta…";
    status.hidden = false;
    const message = addMessage("user", text);
    const messages = [...history, { role: "user", text }];
    try {
      const response = await post("/chat", { messages });
      const answer = await response.json();
      const reply = addMessage("assistant", answer.text);
      history = [...messages, { role: "assistant", text: answer.text }].slice(-4);
      question.value = "";
      status.hidden = true;
      addSpeech(reply, answer);
    } catch (error) {
      message.remove();
      status.textContent = error.message;
    } finally {
      send.disabled = question.disabled = false;
      question.focus();
    }
  });
}
