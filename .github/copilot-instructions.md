<!-- Trivion: guidance for AI coding agents -->
# Copilot instructions for Trivion

Purpose: short, actionable notes so an AI can be immediately productive in this repo.

- **Big picture**: backend is a FastAPI + native WebSocket ASGI app (entry: `backend.principal`).
  - Real-time game state lives in-memory (per-process) under `GerenciadorSalas` and `GerenciadorJogo`.
  - WebSocket rooms use the pattern `sala_{CODIGO}`; broadcasts are performed via a callback injected from `backend.principal`.
  - Logical ordering of player events uses a Lamport clock implemented in `backend.jogo.RelogioLamport`.

- **Key files** (start here):
  - `backend/principal.py` — app setup, WebSocket routing, REST endpoints and static file serving.
  - `backend/jogo.py` — game lifecycle, timers, Lamport ordering, scoring and broadcast API (`definir_broadcast`).
  - `backend/salas.py` — room lifecycle, player join/reconnect, question management.
  - `backend/modelos.py` — dataclasses and enums (`Sessao`, `Sala`, `Jogador`, `EstadoJogo`, `Papel`).
  - `backend/heartbeat.py` — reconnection window and cleanup (timeout = 10s by default).
  - `frontend/` — static UI. `index.html` for players, `admin.html` for admins.

- **Important runtime & developer workflows**:
  - Dev server (Windows): run `iniciar_servidor.bat` or `python -m backend.principal`.
  - Uvicorn (with autoreload): `uvicorn backend.principal:app --host 0.0.0.0 --port 8000 --reload`.
  - Environment variables of interest: `PORT`.
  - Procfile / `render.yaml` present for deploy. `requirements.txt` contains Python deps.

- **Project-specific patterns & gotchas**:
  - State is in-memory: any change must consider that `salas` and `jogos` are process-local. For scaling, shared state is not implemented.
  - Room naming & broadcast hook: broadcasts always target `sala_{codigo}`. `GerenciadorJogo.definir_broadcast` is how the game publishes events; tests/patches should use that same contract.
  - Lamport timestamps: clients supply a `timestamp` with answers; server calls `relogio.atualizar(timestamp_cliente)` in `GerenciadorJogo.processar_resposta` — do not reorder without preserving Lamport semantics.
  - Reconnections: `heartbeat.desconectados` maps `jogador_id` → temporary state; reconnection flow uses the `reconectar` socket event and `salas.reconectar_jogador`.
  - Room cleanup: empty rooms are deleted in `GerenciadorSalas.sair_sala`.

- **REST + WebSocket integration examples**:
  - Start a game (REST): POST `/api/salas/{CODIGO}/jogo/iniciar` (calls `GerenciadorJogo.iniciar`).
  - Player answer (WebSocket): `send({tipo: 'responder', dados: {resposta: 1, timestamp: <client_ts>}})` handled by `_ao_responder` → `processar_resposta`.

- **Testing / local debugging tips**:
  - Use `uvicorn ... --reload` to pick up Python changes.
  - To simulate reconnection, connect/disconnect a client and call the `reconectar` event with the saved `jogador_id` within ~10s.
  - When modifying timers in `backend/jogo.py`, be aware of `self._timer_task` cancellation to avoid orphaned tasks.

- **What to change carefully**:
  - Do not remove or change the `sala_{}` room naming or `definir_broadcast` signature — many components assume this.
  - Avoid moving business logic out of `GerenciadorJogo`/`GerenciadorSalas` without preserving side-effect ordering (Lamport + timers + broadcasts).

If anything below is unclear or you want more examples (e.g., common refactors, unit-test harness suggestions, or a helper to run a headless client), tell me which area to expand.
