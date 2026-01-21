/**
 * Trivion - Painel de Administração
 */

const estadoLocal = {
    conectado: false,
    estadoJogo: 'lobby',
    jogadores: [],
    perguntaAtual: null,
    indicePergunta: 0,
    totalPerguntas: 0,
    distribuicao: [0, 0, 0, 0],
    processando: false // Debounce para ações
};

let conexao = null;

// === SOCKET.IO ===

function inicializarSocket() {
    conexao = io({
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000
    });

    conexao.on('connect', () => {
        estadoLocal.conectado = true;
        atualizarStatusConexao(true);
        adicionarLog('Conectado ao servidor');
        conexao.emit('obter_estado');
    });

    conexao.on('disconnect', () => {
        estadoLocal.conectado = false;
        atualizarStatusConexao(false);
        adicionarLog('Desconectado do servidor');
    });

    conexao.on('jogador_entrou', (dados) => {
        estadoLocal.jogadores = dados.jogadores;
        atualizarListaJogadores();
        adicionarLog(`Jogador entrou: ${dados.jogador.nome}`);
    });

    conexao.on('jogador_saiu', (dados) => {
        estadoLocal.jogadores = dados.jogadores;
        atualizarListaJogadores();
        adicionarLog(`Jogador saiu: ${dados.nome_jogador}`);
    });

    conexao.on('jogador_espera', (dados) => {
        adicionarLog(`Jogador na espera: ${dados.jogador.nome}`);
    });

    conexao.on('contagem', (dados) => {
        estadoLocal.estadoJogo = 'contagem';
        atualizarEstadoJogo();
        adicionarLog(`Contagem: ${dados.segundos}`);
    });

    conexao.on('pergunta', (dados) => {
        estadoLocal.estadoJogo = 'pergunta';
        estadoLocal.perguntaAtual = dados.pergunta;
        estadoLocal.indicePergunta = dados.indice;
        estadoLocal.totalPerguntas = dados.total;
        estadoLocal.distribuicao = [0, 0, 0, 0];

        atualizarEstadoJogo();
        atualizarPreviaPergunta();
        resetarDistribuicao();
        adicionarLog(`Pergunta ${dados.indice + 1}: ${dados.pergunta.texto.substring(0, 50)}...`);
    });

    conexao.on('temporizador', (dados) => {
        const elementoTimer = document.getElementById('stat-timer');
        if (elementoTimer) elementoTimer.textContent = dados.restante + 's';
    });

    conexao.on('jogador_respondeu', (dados) => {
        const elementoRespondido = document.getElementById('stat-answered');
        const elementoEsperando = document.getElementById('stat-waiting');

        if (elementoRespondido) elementoRespondido.textContent = dados.contagem_respostas;
        if (elementoEsperando) {
            elementoEsperando.textContent = dados.total_jogadores - dados.contagem_respostas;
        }
        adicionarLog(`${dados.contagem_respostas}/${dados.total_jogadores} responderam`);
    });

    conexao.on('resultados', (dados) => {
        estadoLocal.estadoJogo = 'resultados';
        estadoLocal.distribuicao = dados.distribuicao;
        estadoLocal.processando = false;

        atualizarEstadoJogo();
        atualizarDistribuicao(dados.distribuicao, dados.resposta_correta);
        atualizarEstadoBotoes();
        adicionarLog('Resultados exibidos');
    });

    conexao.on('podio', (dados) => {
        estadoLocal.estadoJogo = 'podio';
        estadoLocal.processando = false;
        atualizarEstadoJogo();
        atualizarEstadoBotoes();
        adicionarLog('Pódio exibido');
    });

    conexao.on('ranking', (dados) => {
        estadoLocal.estadoJogo = 'ranking';
        estadoLocal.processando = false;
        atualizarEstadoJogo();
        atualizarEstadoBotoes();
        adicionarLog('Ranking exibido');
    });

    conexao.on('jogo_encerrado', (dados) => {
        estadoLocal.estadoJogo = 'lobby';
        estadoLocal.perguntaAtual = null;
        estadoLocal.jogadores = dados.estado.jogadores;
        estadoLocal.processando = false;

        atualizarEstadoJogo();
        atualizarListaJogadores();
        atualizarEstadoBotoes();
        resetarPreviaPergunta();
        adicionarLog('Jogo encerrado');
    });

    conexao.on('estado', (dados) => {
        estadoLocal.estadoJogo = dados.estado;
        estadoLocal.jogadores = dados.jogadores;

        atualizarEstadoJogo();
        atualizarListaJogadores();
        atualizarEstadoBotoes();
    });
}

// === CHAMADAS DE API ===

async function iniciarJogo() {
    if (estadoLocal.processando) return;
    estadoLocal.processando = true;
    atualizarEstadoBotoes();

    try {
        const resposta = await fetch('/api/jogo/iniciar', { method: 'POST' });
        const dados = await resposta.json();

        if (resposta.ok && dados.status === 'ok') {
            adicionarLog('Jogo iniciado!');
        } else {
            adicionarLog(`Erro: ${dados.mensagem || 'Falha ao iniciar'}`);
            estadoLocal.processando = false;
            atualizarEstadoBotoes();
        }
    } catch (erro) {
        adicionarLog(`Erro: ${erro.message}`);
        estadoLocal.processando = false;
        atualizarEstadoBotoes();
    }
}

async function proximaPergunta() {
    if (estadoLocal.processando) return;
    estadoLocal.processando = true;
    atualizarEstadoBotoes();

    try {
        const resposta = await fetch('/api/jogo/proxima', { method: 'POST' });
        const dados = await resposta.json();

        if (resposta.ok && dados.status === 'ok') {
            adicionarLog('Próxima pergunta...');
        } else {
            adicionarLog(`Erro: ${dados.mensagem || 'Falha ao avançar'}`);
            estadoLocal.processando = false;
            atualizarEstadoBotoes();
        }
    } catch (erro) {
        adicionarLog(`Erro: ${erro.message}`);
        estadoLocal.processando = false;
        atualizarEstadoBotoes();
    }
}

async function mostrarRanking() {
    if (estadoLocal.processando) return;
    estadoLocal.processando = true;
    atualizarEstadoBotoes();

    try {
        const resposta = await fetch('/api/jogo/ranking', { method: 'POST' });
        const dados = await resposta.json();

        if (resposta.ok && dados.status === 'ok') {
            adicionarLog('Ranking exibido');
        } else {
            adicionarLog(`Erro: ${dados.mensagem || 'Falha ao mostrar ranking'}`);
            estadoLocal.processando = false;
            atualizarEstadoBotoes();
        }
    } catch (erro) {
        adicionarLog(`Erro: ${erro.message}`);
        estadoLocal.processando = false;
        atualizarEstadoBotoes();
    }
}

async function encerrarJogo() {
    if (estadoLocal.processando) return;

    if (!confirm('Tem certeza que deseja encerrar o jogo?')) return;

    estadoLocal.processando = true;
    atualizarEstadoBotoes();

    try {
        const resposta = await fetch('/api/jogo/encerrar', { method: 'POST' });
        const dados = await resposta.json();

        if (resposta.ok && dados.status === 'ok') {
            adicionarLog('Jogo encerrado');
        } else {
            adicionarLog(`Erro: ${dados.mensagem || 'Falha ao encerrar'}`);
            estadoLocal.processando = false;
            atualizarEstadoBotoes();
        }
    } catch (erro) {
        adicionarLog(`Erro: ${erro.message}`);
        estadoLocal.processando = false;
        atualizarEstadoBotoes();
    }
}

// === ATUALIZAÇÕES DE UI ===

function atualizarStatusConexao(conectado) {
    const ponto = document.getElementById('status-dot');
    const texto = document.getElementById('status-text');

    if (!ponto || !texto) return;

    if (conectado) {
        ponto.classList.add('connected');
        texto.textContent = 'Conectado';
    } else {
        ponto.classList.remove('connected');
        texto.textContent = 'Desconectado';
    }
}

function atualizarEstadoJogo() {
    const rotulosEstado = {
        'lobby': 'LOBBY',
        'contagem': 'CONTAGEM',
        'pergunta': 'PERGUNTA',
        'resultados': 'RESULTADOS',
        'podio': 'PÓDIO',
        'ranking': 'RANKING',
        'finalizado': 'FINALIZADO'
    };

    const elementoEstado = document.getElementById('game-state');
    if (elementoEstado) {
        elementoEstado.textContent =
            rotulosEstado[estadoLocal.estadoJogo] || estadoLocal.estadoJogo.toUpperCase();
    }
}

function atualizarEstadoBotoes() {
    const btnIniciar = document.getElementById('btn-start');
    const btnProxima = document.getElementById('btn-next');
    const btnRanking = document.getElementById('btn-leaderboard');
    const btnEncerrar = document.getElementById('btn-encerrar');

    const emLobby = estadoLocal.estadoJogo === 'lobby';
    const emResultados = estadoLocal.estadoJogo === 'resultados';
    const emPodio = estadoLocal.estadoJogo === 'podio';

    if (btnIniciar) btnIniciar.disabled = !emLobby || estadoLocal.jogadores.length < 1 || estadoLocal.processando;
    if (btnProxima) btnProxima.disabled = !emResultados || estadoLocal.processando;
    if (btnRanking) btnRanking.disabled = !emPodio || estadoLocal.processando;
    if (btnEncerrar) btnEncerrar.disabled = emLobby || estadoLocal.processando;
}

function atualizarListaJogadores() {
    const container = document.getElementById('players-list');
    const elementoContagem = document.getElementById('player-count');

    if (!container || !elementoContagem) return;

    elementoContagem.textContent = estadoLocal.jogadores.length;

    if (estadoLocal.jogadores.length === 0) {
        container.innerHTML = `
            <p style="color: var(--text-secondary); text-align: center; padding: 2rem;">
                Aguardando jogadores...
            </p>
        `;
        return;
    }

    const ordenados = [...estadoLocal.jogadores].sort((a, b) => b.pontuacao - a.pontuacao);

    container.innerHTML = ordenados.map((jogador, indice) => `
        <li class="leaderboard-item">
            <span class="leaderboard-position">${indice + 1}</span>
            <div class="leaderboard-info">
                <div class="avatar" style="width: 32px; height: 32px; font-size: 0.9rem;">
                    ${jogador.nome.charAt(0).toUpperCase()}
                </div>
                <span class="name">${escaparHtml(jogador.nome)}</span>
            </div>
            <span class="leaderboard-score">${jogador.pontuacao}</span>
        </li>
    `).join('');

    const elementoEsperando = document.getElementById('stat-waiting');
    if (elementoEsperando) elementoEsperando.textContent = estadoLocal.jogadores.length;
}

function atualizarPreviaPergunta() {
    if (!estadoLocal.perguntaAtual) return;

    const p = estadoLocal.perguntaAtual;
    const container = document.getElementById('question-preview');

    if (container) {
        container.querySelector('.number').textContent =
            `Pergunta ${estadoLocal.indicePergunta + 1}/${estadoLocal.totalPerguntas}`;
        container.querySelector('.text').textContent = p.texto;
    }

    const containerOpcoes = document.getElementById('options-preview');
    if (containerOpcoes) {
        containerOpcoes.innerHTML = p.opcoes.map((opt, i) => `
            <div class="option-preview" style="padding: 1rem; background: rgba(255,255,255,0.1); border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; gap: 0.5rem;">
                <div style="width: 24px; height: 24px; background: var(--option-${['a', 'b', 'c', 'd'][i]}); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.8rem;">
                    ${['A', 'B', 'C', 'D'][i]}
                </div>
                <span>${escaparHtml(opt)}</span>
            </div>
        `).join('');
    }

    const elementoRespondido = document.getElementById('stat-answered');
    const elementoEsperando = document.getElementById('stat-waiting');
    const elementoTimer = document.getElementById('stat-timer');

    if (elementoRespondido) elementoRespondido.textContent = '0';
    if (elementoEsperando) elementoEsperando.textContent = estadoLocal.jogadores.length;
    if (elementoTimer) elementoTimer.textContent = p.tempo_limite + 's';
}

function resetarPreviaPergunta() {
    const container = document.getElementById('question-preview');
    if (container) {
        container.querySelector('.number').textContent = 'Pergunta 0/0';
        container.querySelector('.text').textContent = 'Aguardando início do jogo...';
    }

    const containerOpcoes = document.getElementById('options-preview');
    if (containerOpcoes) containerOpcoes.innerHTML = '';

    const elementoRespondido = document.getElementById('stat-answered');
    const elementoEsperando = document.getElementById('stat-waiting');
    const elementoTimer = document.getElementById('stat-timer');

    if (elementoRespondido) elementoRespondido.textContent = '0';
    if (elementoEsperando) elementoEsperando.textContent = estadoLocal.jogadores.length;
    if (elementoTimer) elementoTimer.textContent = '--';

    resetarDistribuicao();
}

function resetarDistribuicao() {
    for (let i = 0; i < 4; i++) {
        const elementoBarra = document.getElementById(`dist-${i}`);
        const elementoSoma = document.getElementById(`dist-count-${i}`);
        if (elementoBarra) elementoBarra.style.height = '0%';
        if (elementoSoma) elementoSoma.textContent = '0';
    }
}

function atualizarDistribuicao(distribuicao, indiceCorreto) {
    const total = distribuicao.reduce((a, b) => a + b, 0) || 1;

    for (let i = 0; i < 4; i++) {
        const elementoBarra = document.getElementById(`dist-${i}`);
        const elementoSoma = document.getElementById(`dist-count-${i}`);

        if (elementoBarra) {
            const porcentagem = (distribuicao[i] / total) * 100;
            elementoBarra.style.height = porcentagem + '%';
        }
        if (elementoSoma) elementoSoma.textContent = distribuicao[i];
    }

    const elementosOpcao = document.querySelectorAll('.option-preview');
    elementosOpcao.forEach((el, i) => {
        el.classList.toggle('correct', i === indiceCorreto);
    });
}

function adicionarLog(mensagem) {
    const registro = document.getElementById('log');
    if (!registro) return;

    const hora = new Date().toLocaleTimeString();

    const entrada = document.createElement('div');
    entrada.className = 'log-entry';
    entrada.innerHTML = `<span class="time">[${hora}]</span> ${escaparHtml(mensagem)}`;

    registro.insertBefore(entrada, registro.firstChild);

    while (registro.children.length > 50) {
        registro.removeChild(registro.lastChild);
    }
}

function escaparHtml(texto) {
    const div = document.createElement('div');
    div.textContent = texto;
    return div.innerHTML;
}

// === INICIALIZAÇÃO ===

document.addEventListener('DOMContentLoaded', () => {
    inicializarSocket();

    const btnIniciar = document.getElementById('btn-start');
    const btnProxima = document.getElementById('btn-next');
    const btnRanking = document.getElementById('btn-leaderboard');
    const btnEncerrar = document.getElementById('btn-encerrar');

    if (btnIniciar) btnIniciar.addEventListener('click', iniciarJogo);
    if (btnProxima) btnProxima.addEventListener('click', proximaPergunta);
    if (btnRanking) btnRanking.addEventListener('click', mostrarRanking);
    if (btnEncerrar) btnEncerrar.addEventListener('click', encerrarJogo);

    adicionarLog('Painel admin inicializado');
});
