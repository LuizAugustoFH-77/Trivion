/** Trivion Admin - Controle */

const state = {
    sala: null,
    jogadores: [],
    estado: 'lobby'
};

let ws = null;
let reconnectTimer = null;
let isConnected = false;
const handlers = {};
let timerInterval = null;

function on(tipo, handler) {
    handlers[tipo] = handler;
}

function emit(tipo, dados = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ tipo, dados }));
    }
}

function conectarWebSocket() {
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${protocolo}://${window.location.host}/ws`);

    ws.onopen = () => {
        isConnected = true;
        log('Conectado ao servidor');
        updateStatus('Conectado');

        const code = window.location.pathname.split('/admin/')[1];
        if (code) {
            state.sala = code;
            emit('entrar_sala', { codigo: code, nome: 'ADMIN', como_admin: true });
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
            log('Erro ao processar mensagem do servidor');
        }
    };

    ws.onclose = () => {
        isConnected = false;
        updateStatus(state.estado || 'Offline');
        if (!reconnectTimer) {
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                conectarWebSocket();
            }, 1500);
        }
    };
}

// UI Helpers
const log = (msg) => {
    const el = document.getElementById('log');
    const line = document.createElement('div');
    line.innerHTML = `<span style="color:#666">[${new Date().toLocaleTimeString()}]</span> ${msg}`;
    el.prepend(line);
};

const updateStatus = (st) => {
    state.estado = (st || '').toLowerCase();
    document.getElementById('game-state').textContent = st.toUpperCase();
    document.getElementById('status-dot').style.background = isConnected ? '#10b981' : '#ef4444';
    document.getElementById('status-text').textContent = isConnected ? 'Online' : 'Offline';
    updateButtons();
};

const updateButtons = () => {
    const btnStart = document.getElementById('btn-start');
    const btnNext = document.getElementById('btn-next');
    const btnLeaderboard = document.getElementById('btn-leaderboard');
    const btnVoltarLobby = document.getElementById('btn-voltar-lobby');
    if (btnStart) btnStart.disabled = state.estado !== 'lobby';
    if (btnNext) btnNext.disabled = state.estado !== 'resultados';
    if (btnLeaderboard) btnLeaderboard.disabled = state.estado === 'lobby';
    if (btnVoltarLobby) btnVoltarLobby.disabled = !['podio', 'finalizado'].includes(state.estado);
};

const updateAnsweredStats = (totalRespondidas) => {
    const ativos = state.jogadores.filter(j => j.papel === 'jogador' && !j.em_espera).length;
    const answered = totalRespondidas ?? state.jogadores.filter(j => j.respondeu).length;
    const statAnswered = document.getElementById('stat-answered');
    const statWaiting = document.getElementById('stat-waiting');
    if (statAnswered) statAnswered.textContent = answered;
    if (statWaiting) statWaiting.textContent = Math.max(ativos - answered, 0);
};

const renderDistribuicao = (estatisticas) => {
    if (!estatisticas) return;
    const total = estatisticas.reduce((a, b) => a + b, 0) || 1;
    estatisticas.forEach((v, i) => {
        const bar = document.getElementById(`dist-${i}`);
        const count = document.getElementById(`dist-count-${i}`);
        if (bar) bar.style.height = `${(v / total) * 100}%`;
        if (count) count.textContent = v;
    });
};

const startTimer = (segundos) => {
    if (timerInterval) clearInterval(timerInterval);
    const el = document.getElementById('stat-timer');
    let restante = segundos;
    if (el) el.textContent = restante;
    timerInterval = setInterval(() => {
        restante -= 1;
        if (el) el.textContent = Math.max(restante, 0);
        if (restante <= 0) clearInterval(timerInterval);
    }, 1000);
};

// ACTIONS
const api = async (endpoint) => {
    if (!state.sala) {
        const code = prompt('Informe o código da sala:');
        if (!code) return;
        state.sala = code.trim().toUpperCase();
        if (isConnected) {
            emit('entrar_sala', { codigo: state.sala, nome: 'ADMIN', como_admin: true });
        }
    }

    const res = await fetch(`/api/salas/${state.sala}/jogo/${endpoint}`, { method: 'POST' });
    const data = await res.json();
    if (data.status !== 'ok') {
        log(`Erro: ${data.mensagem || 'Falha'}`);
        return;
    }

    if (endpoint === 'encerrar') {
        log('Jogo encerrado pelo administrador');
        updateStatus('LOBBY');
        updateAnsweredStats(0);
        await fetchEstado();
    }
};

const fetchEstado = async () => {
    const res = await fetch(`/api/salas/${state.sala}/jogo/estado`);
    const data = await res.json();
    updateStatus(data.estado);
    state.jogadores = data.jogadores || [];
    updatePlayers();
    updateAnsweredStats();
};

document.getElementById('btn-start').onclick = () => api('iniciar');
document.getElementById('btn-next').onclick = () => api('proxima');
document.getElementById('btn-encerrar').onclick = () => api('encerrar');
document.getElementById('btn-leaderboard').onclick = () => fetchEstado();
document.getElementById('btn-voltar-lobby').onclick = async () => {
    const ok = confirm('Voltar todos os jogadores ao lobby para uma nova partida?');
    if (!ok) return;
    try {
        const res = await fetch(`/api/salas/${state.sala}/jogo/voltar-lobby`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            log('Jogadores voltaram ao lobby');
            updateStatus('LOBBY');
            await fetchEstado();
        } else {
            log(`Erro: ${data.detail || 'Falha'}`);
        }
    } catch (err) {
        log('Erro ao voltar ao lobby (falha de rede).');
    }
};
document.getElementById('btn-delete-room').onclick = async () => {
    if (!state.sala) {
        const code = prompt('Informe o código da sala para excluir:');
        if (!code) return;
        state.sala = code.trim().toUpperCase();
    }
    const ok = confirm('Tem certeza que deseja excluir a sala? Todos serão removidos.');
    if (!ok) return;
    try {
        const res = await fetch(`/api/salas/${state.sala}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            window.location.href = '/';
        } else {
            log(`Erro ao excluir sala: ${data.mensagem || 'Falha'}`);
        }
    } catch (err) {
        log('Erro ao excluir sala (falha de rede).');
    }
};

// SOCKET
on('bem_vindo', ({ sala, estado }) => {
    log(`Conectado à sala ${sala.codigo}`);
    state.jogadores = estado.jogadores;
    updatePlayers();
    updateStatus(estado.estado);
    updateAnsweredStats();
});

on('jogador_entrou', ({ jogador, jogadores }) => {
    log(`${jogador.nome} entrou`);
    state.jogadores = jogadores;
    updatePlayers();
    updateAnsweredStats();
});

on('jogador_saiu', ({ nome, jogadores }) => {
    log(`${nome} saiu`);
    if (jogadores) state.jogadores = jogadores;
    updatePlayers();
    updateAnsweredStats();
});

on('jogador_respondeu', ({ total_respostas }) => {
    updateAnsweredStats(total_respostas);
});

on('estado', (est) => {
    updateStatus(est.estado);
    state.jogadores = est.jogadores || state.jogadores;
    updatePlayers();
    updateAnsweredStats();
});

on('pergunta', ({ pergunta, numero, total }) => {
    log(`Pergunta ${numero}: ${pergunta.texto}`);
    document.getElementById('question-preview').querySelector('.text').textContent = pergunta.texto;
    document.getElementById('question-preview').querySelector('.number').textContent = `Pergunta ${numero}/${total}`;
    updateStatus('PERGUNTA');
    startTimer(pergunta.tempo);

    // Atualiza preview de opções
    const opts = document.getElementById('options-preview');
    opts.innerHTML = pergunta.opcoes.map((o, i) => `
        <div style="padding:0.5rem; background:rgba(255,255,255,0.1); border-radius:4px; margin-bottom:4px">
            <b>${['A', 'B', 'C', 'D'][i]}</b> ${o}
        </div>
    `).join('');
});

on('resultados', ({ ranking, estatisticas }) => {
    log('Resultados exibidos');
    updateStatus('RESULTADOS');
    renderDistribuicao(estatisticas);
});

on('podio_completo', () => {
    log('Pódio exibido');
    updateStatus('PODIO');
});

on('jogo_encerrado', () => {
    log('Jogo encerrado');
    updateStatus('LOBBY');
    updateAnsweredStats(0);
});

on('sala_encerrada', () => {
    log('Sala encerrada');
    window.location.href = '/';
});

on('voltou_lobby', ({ jogadores }) => {
    log('Jogadores voltaram ao lobby');
    state.jogadores = jogadores || state.jogadores;
    updatePlayers();
    updateStatus('LOBBY');
    updateAnsweredStats(0);
});

conectarWebSocket();

function updatePlayers() {
    document.getElementById('player-count').textContent = state.jogadores.length;
    const list = document.getElementById('players-list');

    list.innerHTML = state.jogadores
        .sort((a, b) => b.pontuacao - a.pontuacao)
        .map((j, i) => `
            <div style="padding:0.5rem; border-bottom:1px solid rgba(255,255,255,0.1); display:flex; justify-content:space-between; align-items:center">
                <span>#${i + 1} ${j.nome}${j.em_espera ? ' ⏳' : ''}${j.papel === 'admin' ? ' 👑' : ''}</span>
                <div style="display:flex; align-items:center; gap:0.5rem">
                    <span>${j.pontuacao}</span>
                    ${j.papel !== 'admin' ? `<button onclick="kickPlayer('${j.id}', '${j.nome}')" class="btn-kick" title="Expulsar">✕</button>` : ''}
                </div>
            </div>
        `).join('');
}

async function kickPlayer(jogadorId, nome) {
    const ok = confirm(`Tem certeza que deseja expulsar "${nome}" da sala?`);
    if (!ok) return;

    try {
        const res = await fetch(`/api/salas/${state.sala}/jogadores/${jogadorId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            log(`${nome} foi expulso da sala`);
        } else {
            log(`Erro ao expulsar: ${data.detail || 'Falha'}`);
        }
    } catch (err) {
        log('Erro ao expulsar jogador (falha de rede).');
    }
}

on('jogador_expulso', ({ nome, jogadores }) => {
    log(`${nome} foi expulso`);
    state.jogadores = jogadores;
    updatePlayers();
    updateAnsweredStats();
});
