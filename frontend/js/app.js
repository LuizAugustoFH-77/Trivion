/**
 * Trivion - Cliente
 */

const state = {
    sala: null,
    senha: null,
    jogador: null,
    estado: 'lobby',
    pergunta: null,
    jogadores: [],
    ultimaResposta: null,
    tempoRespostaMs: null,
    pontuacaoAntes: 0,
    questionStartTime: null,
    aguardandoProxima: false
};

const screens = {
    rooms: document.getElementById('screen-rooms'),
    join: document.getElementById('screen-join'),
    lobby: document.getElementById('screen-lobby'),
    countdown: document.getElementById('screen-countdown'),
    question: document.getElementById('screen-question'),
    waiting: document.getElementById('screen-waiting'),
    result: document.getElementById('screen-result'),
    drumroll: document.getElementById('screen-drumroll'),
    podium: document.getElementById('screen-podium'),
    leaderboard: document.getElementById('screen-leaderboard'),
    editor: document.getElementById('screen-question-editor'),
    espera: document.getElementById('screen-espera')
};

let ws = null;
let reconnectTimer = null;
let isConnected = false;
let lamport = 0;
const handlers = {};

function on(tipo, handler) {
    handlers[tipo] = handler;
}

function emit(tipo, dados = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo, dados }));
    }
}

function atualizarLamport(recebido) {
    if (typeof recebido === 'number') {
        lamport = Math.max(lamport, recebido) + 1;
    } else {
        lamport += 1;
    }
    return lamport;
}

function conectarWebSocket() {
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${protocolo}://${window.location.host}/ws`);

    ws.onopen = () => {
        isConnected = true;
        showConnectionOverlay(false);

        const stored = loadReconnectInfo();
        if (stored?.jogador_id && !state.jogador) {
            emit('reconectar', { jogador_id: stored.jogador_id });
        }

        const urlCode = parseRoomCodeFromUrl();
        if (urlCode) {
            state.sala = urlCode;
            document.getElementById('room-code-display').textContent = `Sala: ${urlCode}`;
            showScreen('join');
        } else {
            emit('listar_salas');
            showScreen('rooms');
        }
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            const tipo = msg?.tipo;
            const dados = msg?.dados;
            if (tipo === 'ping_heartbeat') {
                emit('pong_heartbeat');
                return;
            }
            const handler = handlers[tipo];
            if (handler) handler(dados);
        } catch (err) {
            console.error('Erro ao processar mensagem', err);
        }
    };

    ws.onclose = () => {
        isConnected = false;
        if (state.jogador?.id) showConnectionOverlay(true);
        if (!reconnectTimer) {
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                conectarWebSocket();
            }, 1500);
        }
    };
}

let countdownInterval = null;
let questionInterval = null;
const TIMER_CIRC = 283;

// === UI HELPERS ===
function showScreen(id) {
    state.estado = id;
    Object.values(screens).forEach(el => {
        if (el) el.classList.remove('active');
    });
    const target = screens[id];
    if (target) target.classList.add('active');
}

function closeModals() {
    document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
}

function showError(elId, msg) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
}

function clearError(elId) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = '';
    el.classList.add('hidden');
}

function showConnectionOverlay(show) {
    const el = document.getElementById('connection-overlay');
    if (!el) return;
    if (show) el.classList.remove('hidden');
    else el.classList.add('hidden');
}

function parseRoomCodeFromUrl() {
    const parts = window.location.pathname.split('/sala/');
    return parts[1] ? parts[1].toUpperCase() : null;
}

function saveReconnectInfo() {
    if (!state.jogador?.id || !state.sala) return;
    localStorage.setItem('trivion_reconnect', JSON.stringify({
        jogador_id: state.jogador.id,
        sala_codigo: state.sala
    }));
}

function loadReconnectInfo() {
    try {
        return JSON.parse(localStorage.getItem('trivion_reconnect') || 'null');
    } catch {
        return null;
    }
}

function clearReconnectInfo() {
    localStorage.removeItem('trivion_reconnect');
}

function stopTimers() {
    if (countdownInterval) clearInterval(countdownInterval);
    if (questionInterval) clearInterval(questionInterval);
    countdownInterval = null;
    questionInterval = null;
}

function startCountdown(segundos) {
    stopTimers();
    const el = document.getElementById('countdown-number');
    let restante = segundos;
    if (el) el.textContent = restante;
    countdownInterval = setInterval(() => {
        restante -= 1;
        if (el) el.textContent = Math.max(restante, 0);
        if (restante <= 0) clearInterval(countdownInterval);
    }, 1000);
}

function startQuestionTimer(segundos) {
    stopTimers();
    const textEl = document.getElementById('timer-text');
    const progressEl = document.getElementById('timer-progress');
    const inicio = Date.now();
    state.questionStartTime = inicio;

    const update = () => {
        const decorrido = (Date.now() - inicio) / 1000;
        const restante = Math.max(0, Math.ceil(segundos - decorrido));
        if (textEl) textEl.textContent = restante;
        if (progressEl) {
            const frac = Math.min(decorrido / segundos, 1);
            const offset = TIMER_CIRC * frac;
            progressEl.style.strokeDashoffset = `${offset}`;
        }
        if (decorrido >= segundos) clearInterval(questionInterval);
    };

    update();
    questionInterval = setInterval(update, 250);
}

function updateLobby(jogadores) {
    if (!jogadores) return;
    state.jogadores = jogadores;
    const self = state.jogadores.find(j => j.id === state.jogador?.id);
    if (self) state.jogador = { ...state.jogador, ...self };

    const grid = document.getElementById('players-list');
    if (grid) {
        grid.innerHTML = jogadores.map(j => `
            <div class="player-chip ${j.id === state.jogador?.id ? 'self' : ''}">
                <div class="avatar">${j.nome[0] || '?'}</div>
                <span>${j.nome}</span>
                <span>${j.pontuacao}pts</span>
            </div>
        `).join('');
    }
    const count = document.getElementById('player-count');
    if (count) count.textContent = jogadores.length;
}

function updateAnsweredCount(totalRespondidas) {
    const answered = document.getElementById('answered-count');
    const total = document.getElementById('total-players');
    const ativos = state.jogadores.filter(j => j.papel === 'jogador' && !j.em_espera).length;
    if (answered) answered.textContent = totalRespondidas ?? 0;
    if (total) total.textContent = ativos;
}

function renderQuestion(p, current = 1, total = 1) {
    if (!p) return;
    document.getElementById('question-text').textContent = p.texto;
    document.getElementById('question-progress').textContent = `${current}/${total}`;
    document.getElementById('timer-text').textContent = p.tempo;
    startQuestionTimer(p.tempo);

    const grid = document.querySelector('.options-grid');
    if (grid) {
        grid.innerHTML = p.opcoes.map((opt, i) => `
            <button class="option-btn option-${['a', 'b', 'c', 'd'][i]}" onclick="answer(${i})">
                <span class="option-icon">${['A', 'B', 'C', 'D'][i]}</span>
                <span>${opt}</span>
            </button>
        `).join('');
    }
}

function syncFromEstado(estado) {
    if (!estado) return;
    updateLobby(estado.jogadores || []);

    if (state.jogador?.em_espera && estado.estado !== 'lobby') {
        showScreen('espera');
        return;
    }

    if (state.aguardandoProxima && estado.estado !== 'contagem' && estado.estado !== 'pergunta') {
        showScreen('espera');
        return;
    }

    if (estado.estado === 'contagem') {
        state.aguardandoProxima = false;
        showScreen('countdown');
        startCountdown(3);
    } else if (estado.estado === 'pergunta') {
        state.aguardandoProxima = false;
        state.pergunta = estado.pergunta;
        state.ultimaResposta = null;
        state.tempoRespostaMs = null;
        state.pontuacaoAntes = (state.jogadores.find(j => j.id === state.jogador?.id)?.pontuacao) || 0;
        renderQuestion(estado.pergunta, estado.pergunta_atual + 1, estado.total_perguntas);
        showScreen('question');
    } else if (estado.estado === 'resultados') {
        showScreen('result');
    } else if (estado.estado === 'podio') {
        showScreen('podium');
    } else if (estado.estado === 'finalizado') {
        showScreen('leaderboard');
    } else {
        showScreen('lobby');
    }
}

// === SOCKET EVENTS ===

on('reconexao_sucesso', ({ jogador_id, nome, sala_codigo, pontuacao, em_espera }) => {
    state.jogador = { id: jogador_id, nome, pontuacao, em_espera };
    state.sala = sala_codigo;
    state.aguardandoProxima = false;
    saveReconnectInfo();
    showConnectionOverlay(false);
    emit('obter_estado');
});

on('reconexao_falhou', () => {
    clearReconnectInfo();
    showConnectionOverlay(false);
    emit('listar_salas');
    showScreen('rooms');
});

on('salas_disponiveis', ({ salas }) => {
    const list = document.getElementById('rooms-list');
    if (!list) return;
    list.innerHTML = salas.length ? '' : '<p class="no-rooms">Nenhuma sala encontrada.</p>';

    salas.forEach(sala => {
        const div = document.createElement('div');
        div.className = 'room-card';
        div.innerHTML = `
            <div>
                <h3>${sala.nome}</h3>
                <small>Código: ${sala.codigo} | ${sala.jogadores} jogadores</small>
            </div>
            <button onclick="enterRoom('${sala.codigo}', '${sala.nome}')" class="btn-primary">Entrar</button>
        `;
        list.appendChild(div);
    });
});

on('sala_criada', ({ sala, codigo }) => {
    state.sala = codigo;
    state.aguardandoProxima = false;
    document.getElementById('editor-room-code').textContent = codigo;
    closeModals();
    showScreen('editor');
    loadQuestions();
});

on('bem_vindo', ({ jogador, sala, estado }) => {
    state.jogador = jogador;
    state.sala = sala.codigo;
    state.senha = null;
    state.aguardandoProxima = false;
    saveReconnectInfo();
    syncFromEstado(estado);
});

on('jogador_entrou', ({ jogadores }) => updateLobby(jogadores));

on('jogador_saiu', ({ jogadores }) => {
    if (jogadores) updateLobby(jogadores);
});

on('contagem', ({ segundos }) => {
    if (state.jogador?.em_espera) {
        showScreen('espera');
        return;
    }
    state.aguardandoProxima = false;
    showScreen('countdown');
    startCountdown(segundos);
});

on('pergunta', ({ pergunta, numero, total, timestamp }) => {
    if (state.jogador?.em_espera) {
        showScreen('espera');
        return;
    }
    state.aguardandoProxima = false;
    state.pergunta = pergunta;
    if (typeof timestamp === 'number') atualizarLamport(timestamp);
    state.ultimaResposta = null;
    state.tempoRespostaMs = null;
    state.pontuacaoAntes = (state.jogadores.find(j => j.id === state.jogador?.id)?.pontuacao) || 0;
    renderQuestion(pergunta, numero, total);
    showScreen('question');
});

on('jogador_respondeu', ({ total_respostas }) => {
    updateAnsweredCount(total_respostas);
});

on('resultados', ({ ranking, correta, estatisticas }) => {
    if (state.jogador?.em_espera) {
        showScreen('espera');
        return;
    }
    showScreen('result');

    const correctText = document.getElementById('result-answer');
    const feedback = document.getElementById('result-feedback');
    const rankingEl = document.getElementById('result-ranking');
    const timeEl = document.getElementById('result-time');

    if (correctText && state.pergunta) {
        correctText.textContent = `Correta: ${state.pergunta.opcoes[correta]}`;
    }

    if (feedback) {
        const acertou = state.ultimaResposta === correta;
        feedback.textContent = acertou ? '✅ Você acertou!' : '❌ Você errou';
    }

    if (timeEl) {
        if (state.tempoRespostaMs != null && state.ultimaResposta != null) {
            timeEl.style.display = 'block';
            timeEl.textContent = `Tempo: ${(state.tempoRespostaMs / 1000).toFixed(1)}s`;
        } else {
            timeEl.style.display = 'none';
        }
    }

    if (rankingEl) {
        rankingEl.innerHTML = ranking.slice(0, 5).map((j, i) => `
            <li>#${i + 1} ${j.nome} - ${j.pontuacao} pts</li>
        `).join('');
    }

    // Atualiza pontos ganhos nesta rodada
    const pointsEl = document.getElementById('result-points');
    if (pointsEl && state.jogador) {
        const meuResultado = ranking.find(j => j.id === state.jogador.id);
        if (meuResultado && meuResultado.pontos_ultima_pergunta > 0) {
            pointsEl.style.display = 'block';
            pointsEl.textContent = `+${meuResultado.pontos_ultima_pergunta} pontos`;
            pointsEl.className = 'result-points correct-glow'; // Add a glow class if you want
            pointsEl.style.color = 'var(--accent-cyan)';
        } else if (meuResultado && state.ultimaResposta != null) {
            // Errou
            pointsEl.style.display = 'block';
            pointsEl.textContent = '0 pontos';
            pointsEl.className = 'result-points';
            pointsEl.style.color = 'var(--accent-red)';
        } else {
            // Não respondeu (timeout) ou era admin/espera
            pointsEl.style.display = 'none';
        }
    }

    emit('obter_estado');
});

on('podio_inicio', () => {
    showScreen('drumroll');
    ['podium-1', 'podium-2', 'podium-3'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
});

on('podio_posicao', ({ posicao, jogador }) => {
    const el = document.getElementById(`podium-${posicao}`);
    if (!el) return;
    el.classList.remove('hidden');
    el.querySelector('.podium-name').textContent = jogador.nome;
    el.querySelector('.podium-score').textContent = `${jogador.pontuacao} pts`;
});

on('podio_completo', ({ ranking }) => {
    showScreen('podium');

    const list = document.getElementById('leaderboard-list');
    if (list) {
        list.innerHTML = ranking.map((j, i) => `
            <li>#${i + 1} ${j.nome} - ${j.pontuacao} pts</li>
        `).join('');
    }

    setTimeout(() => {
        showScreen('leaderboard');
    }, 4000);
});

on('jogo_encerrado', ({ jogadores }) => {
    if (jogadores) updateLobby(jogadores);
    if (state.jogador) state.jogador.em_espera = false;
    if (state.aguardandoProxima) {
        showScreen('espera');
    } else {
        showScreen('lobby');
    }
});

on('sala_encerrada', () => {
    clearReconnectInfo();
    state.sala = null;
    state.senha = null;
    state.jogador = null;
    state.aguardandoProxima = false;
    showScreen('rooms');
    emit('listar_salas');
});

on('expulso', ({ mensagem }) => {
    clearReconnectInfo();
    alert(mensagem || 'Você foi removido da sala');
    state.sala = null;
    state.senha = null;
    state.jogador = null;
    state.aguardandoProxima = false;
    showScreen('rooms');
    emit('listar_salas');
});

on('jogador_expulso', ({ nome, jogadores }) => {
    if (jogadores) updateLobby(jogadores);
});

on('voltou_lobby', ({ jogadores }) => {
    if (jogadores) updateLobby(jogadores);
    if (state.jogador) state.jogador.em_espera = false;
    state.aguardandoProxima = false;
    showScreen('lobby');
});

on('estado', (dados) => {
    state.estado = dados.estado;
    syncFromEstado(dados);
});

on('erro', ({ mensagem }) => {
    if (!mensagem) return;
    if (mensagem.toLowerCase().includes('senha')) {
        showError('password-error', mensagem);
        const roomName = document.getElementById('password-room-name');
        if (roomName && state.sala) roomName.textContent = `Sala: ${state.sala}`;
        const inputPwd = document.getElementById('input-password');
        if (inputPwd) inputPwd.value = '';
        document.getElementById('modal-enter-password').classList.remove('hidden');
        return;
    }
    if (state.estado === 'join') {
        showError('join-error', mensagem);
        return;
    }
    alert(mensagem);
});

// === FUNÇÕES ===

function enterRoom(codigo) {
    state.sala = codigo.toUpperCase();
    state.senha = null;
    state.aguardandoProxima = false;
    document.getElementById('room-code-display').textContent = `Sala: ${state.sala}`;
    showScreen('join');
}

function joinSala() {
    clearError('join-error');
    const nome = document.getElementById('player-name').value.trim();
    if (nome && state.sala) {
        state.aguardandoProxima = false;
        emit('entrar_sala', {
            codigo: state.sala,
            nome,
            senha: state.senha || undefined
        });
    } else {
        showError('join-error', 'Informe o seu nome.');
    }
}

function leaveRoom() {
    if (state.sala) {
        emit('sair_sala');
        state.sala = null;
        state.senha = null;
        state.jogador = null;
        state.aguardandoProxima = false;
        clearReconnectInfo();
        showScreen('rooms');
        emit('listar_salas');
    }
}

// Make globally accessible for onclick
window.leaveRoom = leaveRoom;

function answer(index) {
    if (state.estado !== 'question') return;
    if (state.jogador?.em_espera) return;
    state.ultimaResposta = index;
    state.tempoRespostaMs = state.questionStartTime ? (Date.now() - state.questionStartTime) : null;
    const ts = atualizarLamport();
    emit('responder', {
        resposta: index,
        timestamp: ts
    });
    showScreen('waiting');
}

// === ACTIONS LIGADAS AO DOM ===

const btnCreateRoom = document.getElementById('btn-create-room');
if (btnCreateRoom) {
    btnCreateRoom.onclick = () => {
        clearError('create-room-error');
        document.getElementById('modal-create-room').classList.remove('hidden');
    };
}

const btnConfirmCreate = document.getElementById('btn-confirm-create');
if (btnConfirmCreate) {
    btnConfirmCreate.onclick = () => {
        console.log('Tentando criar sala...');
        clearError('create-room-error');
        const nome = document.getElementById('input-room-name').value.trim();
        const isPrivate = document.getElementById('btn-private').classList.contains('active');
        const senha = document.getElementById('input-room-password').value.trim();

        if (!nome) {
            showError('create-room-error', 'Nome da sala é obrigatório.');
            return;
        }
        if (isPrivate && !senha) {
            showError('create-room-error', 'Senha é obrigatória para sala privada.');
            return;
        }

        if (!ws || ws.readyState !== WebSocket.OPEN) {
            showError('create-room-error', 'Sem conexão com o servidor. Aguarde...');
            conectarWebSocket();
            return;
        }

        console.log('Emitindo criar_sala:', { nome, publica: !isPrivate });
        emit('criar_sala', { nome, publica: !isPrivate, senha: senha || null });
    };
}

const btnCancelCreate = document.getElementById('btn-cancel-create');
if (btnCancelCreate) btnCancelCreate.onclick = closeModals;

const btnBack = document.getElementById('btn-back');
if (btnBack) {
    btnBack.onclick = () => {
        showScreen('rooms');
        emit('listar_salas');
    };
}

const btnJoin = document.getElementById('btn-join');
if (btnJoin) btnJoin.onclick = joinSala;

const btnConfirmPassword = document.getElementById('btn-confirm-password');
if (btnConfirmPassword) {
    btnConfirmPassword.onclick = () => {
        const senha = document.getElementById('input-password').value.trim();
        if (!senha) {
            showError('password-error', 'Informe a senha da sala.');
            return;
        }
        state.senha = senha;
        closeModals();
        joinSala();
    };
}

const btnCancelPassword = document.getElementById('btn-cancel-password');
if (btnCancelPassword) btnCancelPassword.onclick = closeModals;

const btnPublic = document.getElementById('btn-public');
const btnPrivate = document.getElementById('btn-private');
if (btnPublic && btnPrivate) {
    btnPublic.onclick = () => {
        btnPublic.classList.add('active');
        btnPrivate.classList.remove('active');
        document.getElementById('password-group').classList.add('hidden');
    };
    btnPrivate.onclick = () => {
        btnPrivate.classList.add('active');
        btnPublic.classList.remove('active');
        document.getElementById('password-group').classList.remove('hidden');
    };
}

const btnAddQuestion = document.getElementById('btn-add-question');
if (btnAddQuestion) {
    btnAddQuestion.onclick = async () => {
        const texto = document.getElementById('edit-question-text').value.trim();
        const opcoes = [
            document.getElementById('edit-opt-a').value.trim(),
            document.getElementById('edit-opt-b').value.trim(),
            document.getElementById('edit-opt-c').value.trim(),
            document.getElementById('edit-opt-d').value.trim()
        ];
        const correta = parseInt(document.getElementById('edit-correct').value, 10);
        const tempo = parseInt(document.getElementById('edit-time').value, 10) || 20;

        if (!texto || opcoes.some(o => !o)) {
            alert('Preencha a pergunta e todas as opções.');
            return;
        }

        await fetch(`/api/salas/${state.sala}/perguntas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto, opcoes, correta, tempo_limite: tempo })
        });

        document.getElementById('edit-question-text').value = '';
        document.getElementById('edit-opt-a').value = '';
        document.getElementById('edit-opt-b').value = '';
        document.getElementById('edit-opt-c').value = '';
        document.getElementById('edit-opt-d').value = '';

        loadQuestions();
    };
}

const btnFinishEditor = document.getElementById('btn-finish-editor');
if (btnFinishEditor) {
    btnFinishEditor.onclick = async () => {
        const res = await fetch(`/api/salas/${state.sala}/perguntas`);
        const data = await res.json();
        if (!data.perguntas.length) {
            alert('Adicione pelo menos uma pergunta.');
            return;
        }
        window.location.href = `/admin/${state.sala}`;
    };
}

const btnPlayAgain = document.getElementById('btn-play-again');
if (btnPlayAgain) {
    btnPlayAgain.onclick = () => {
        // Vai direto para o lobby aguardando nova partida
        state.aguardandoProxima = false;
        if (state.jogador) state.jogador.em_espera = false;
        showScreen('lobby');
        emit('obter_estado');
    };
}

async function loadQuestions() {
    const res = await fetch(`/api/salas/${state.sala}/perguntas`);
    const data = await res.json();
    const list = document.getElementById('editor-questions-list');
    const badge = document.getElementById('questions-count-badge');
    if (badge) badge.textContent = `${data.perguntas.length} Perguntas`;
    if (!list) return;
    list.innerHTML = data.perguntas.length
        ? data.perguntas.map((p, i) => `<div>${i + 1}. ${p.texto}</div>`).join('')
        : '<p class="empty-msg">Nenhuma pergunta adicionada ainda.</p>';
}

conectarWebSocket();
