/**
 * Trivion - Cliente JavaScript
 */

const estadoLocal = {
    jogador: null,
    jogadores: [],
    perguntaAtual: null,
    indicePergunta: 0,
    totalPerguntas: 0,
    tempoLimite: 20,
    jaRespondeu: false,
    emEspera: false
};

let conexao = null;

const telas = {
    entrar: document.getElementById('screen-join'),
    lobby: document.getElementById('screen-lobby'),
    espera: document.getElementById('screen-espera'),
    contagem: document.getElementById('screen-countdown'),
    pergunta: document.getElementById('screen-question'),
    aguardando: document.getElementById('screen-waiting'),
    resultado: document.getElementById('screen-result'),
    podio: document.getElementById('screen-podium'),
    ranking: document.getElementById('screen-leaderboard')
};


// === NAVEGAÇÃO ===

function mostrarTela(nomeTela) {
    Object.values(telas).forEach(tela => {
        if (tela) tela.classList.remove('active');
    });

    const telaAlvo = telas[nomeTela];
    if (telaAlvo) {
        setTimeout(() => {
            telaAlvo.classList.add('active');
        }, 50);
    }
}


// === SOCKET.IO ===

function inicializarSocket() {
    conexao = io({
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
    });

    conexao.on('connect', () => {
        console.log('✓ Conectado ao servidor');
        esconderSobreposicaoConexao();

        if (estadoLocal.jogador) {
            conexao.emit('entrar', { nome: estadoLocal.jogador.nome });
        }
    });

    conexao.on('disconnect', () => {
        console.log('✗ Desconectado do servidor');
        mostrarSobreposicaoConexao();
    });

    conexao.on('connect_error', (erro) => {
        console.error('Erro de conexão:', erro);
        mostrarSobreposicaoConexao();
    });

    // Evento: Bem-vindo (entrada normal)
    conexao.on('bem_vindo', (dados) => {
        console.log('Bem-vindo!', dados);
        estadoLocal.jogador = dados.jogador;
        estadoLocal.emEspera = false;
        atualizarEstadoDoServidor(dados.estado);
        mostrarTela('lobby');
    });

    // Evento: Em espera (partida em andamento)
    conexao.on('em_espera', (dados) => {
        console.log('Em espera:', dados);
        estadoLocal.jogador = dados.jogador;
        estadoLocal.emEspera = true;
        mostrarTela('espera');
    });

    // Evento: Jogo encerrado (jogadores da espera entram no lobby)
    conexao.on('jogo_encerrado', (dados) => {
        console.log('Jogo encerrado:', dados);
        estadoLocal.jaRespondeu = false;
        estadoLocal.emEspera = false;
        atualizarEstadoDoServidor(dados.estado);
        mostrarTela('lobby');
    });

    conexao.on('jogador_entrou', (dados) => {
        console.log('Jogador entrou:', dados);
        estadoLocal.jogadores = dados.jogadores;
        atualizarListaJogadores();
    });

    conexao.on('jogador_saiu', (dados) => {
        console.log('Jogador saiu:', dados);
        estadoLocal.jogadores = dados.jogadores;
        atualizarListaJogadores();
    });

    conexao.on('contagem', (dados) => {
        console.log('Contagem:', dados.segundos);
        mostrarTela('contagem');
        atualizarContagem(dados.segundos);
    });

    conexao.on('pergunta', (dados) => {
        console.log('Pergunta recebida:', dados);
        estadoLocal.perguntaAtual = dados.pergunta;
        estadoLocal.indicePergunta = dados.indice;
        estadoLocal.totalPerguntas = dados.total;
        estadoLocal.tempoLimite = dados.pergunta.tempo_limite;
        estadoLocal.jaRespondeu = false;

        exibirPergunta(dados);
        mostrarTela('pergunta');
    });

    conexao.on('temporizador', (dados) => {
        atualizarTimer(dados.restante);
    });

    conexao.on('jogador_respondeu', (dados) => {
        console.log('Jogador respondeu:', dados);
        if (estadoLocal.jaRespondeu) {
            atualizarContagemEspera(dados.contagem_respostas, dados.total_jogadores);
        }
    });

    conexao.on('resultados', (dados) => {
        console.log('Resultados:', dados);
        exibirResultados(dados);
        mostrarTela('resultado');
    });

    conexao.on('podio', (dados) => {
        console.log('Pódio:', dados);
        exibirPodio(dados.podio);
        mostrarTela('podio');
    });

    conexao.on('ranking', (dados) => {
        console.log('Ranking:', dados);
        exibirRanking(dados.ranking);
        mostrarTela('ranking');
    });

    conexao.on('estado', (dados) => {
        console.log('Estado:', dados);
        atualizarEstadoDoServidor(dados);
    });

    conexao.on('erro', (dados) => {
        console.error('Erro:', dados.mensagem);
        mostrarErro(dados.mensagem);
    });
}


// === ATUALIZAÇÃO DE UI ===

function atualizarEstadoDoServidor(dados) {
    estadoLocal.jogadores = dados.jogadores || [];
    atualizarListaJogadores();
}

function atualizarListaJogadores() {
    const container = document.getElementById('players-list');
    const elementoContagem = document.getElementById('player-count');

    if (!container || !elementoContagem) return;

    container.innerHTML = '';

    estadoLocal.jogadores.forEach(jogador => {
        const chip = document.createElement('div');
        chip.className = 'player-chip' + (estadoLocal.jogador && jogador.id === estadoLocal.jogador.id ? ' self' : '');

        const inicial = jogador.nome.charAt(0).toUpperCase();
        chip.innerHTML = `
            <div class="avatar">${inicial}</div>
            <span>${escaparHtml(jogador.nome)}</span>
        `;
        container.appendChild(chip);
    });

    elementoContagem.textContent = estadoLocal.jogadores.length;
}

function atualizarContagem(segundos) {
    const elemento = document.getElementById('countdown-number');
    if (!elemento) return;

    elemento.textContent = segundos;
    elemento.style.animation = 'none';
    elemento.offsetHeight;
    elemento.style.animation = 'countdownPop 1s ease';
}

function exibirPergunta(dados) {
    const pergunta = dados.pergunta;

    const elementoProgresso = document.getElementById('question-progress');
    if (elementoProgresso) {
        elementoProgresso.textContent = `${dados.indice + 1}/${dados.total}`;
    }

    const elementoTexto = document.getElementById('question-text');
    if (elementoTexto) {
        elementoTexto.textContent = pergunta.texto;
    }

    pergunta.opcoes.forEach((opcao, indice) => {
        const elementoOpcao = document.getElementById(`option-${indice}`);
        if (elementoOpcao) {
            elementoOpcao.textContent = opcao;
        }
    });

    document.querySelectorAll('.option-btn').forEach(btn => {
        btn.disabled = false;
        btn.classList.remove('selected');
    });

    atualizarTimer(pergunta.tempo_limite);
}

function atualizarTimer(restante) {
    const elementoTexto = document.getElementById('timer-text');
    const elementoProgresso = document.getElementById('timer-progress');

    if (elementoTexto) {
        elementoTexto.textContent = restante;
    }

    if (elementoProgresso) {
        const porcentagem = restante / estadoLocal.tempoLimite;
        const offset = 283 * (1 - porcentagem);
        elementoProgresso.style.strokeDashoffset = offset;

        elementoProgresso.classList.remove('warning', 'danger');
        if (restante <= 5) {
            elementoProgresso.classList.add('danger');
        } else if (restante <= 10) {
            elementoProgresso.classList.add('warning');
        }
    }
}

function atualizarContagemEspera(respondido, total) {
    const elementoRespondido = document.getElementById('answered-count');
    const elementoTotal = document.getElementById('total-players');

    if (elementoRespondido) elementoRespondido.textContent = respondido;
    if (elementoTotal) elementoTotal.textContent = total;
}

function exibirResultados(dados) {
    const meuResultado = dados.resultados.find(r => r.id_jogador === estadoLocal.jogador?.id);

    const elementoFeedback = document.getElementById('result-feedback');
    if (elementoFeedback) {
        elementoFeedback.className = 'result-feedback ' + (meuResultado?.correta ? 'correct' : 'incorrect');
    }

    const opcaoCorreta = estadoLocal.perguntaAtual?.opcoes[dados.resposta_correta] || '';
    const elementoRespostaCorreta = document.getElementById('result-answer');
    if (elementoRespostaCorreta) {
        elementoRespostaCorreta.textContent = `Resposta correta: ${opcaoCorreta}`;
    }

    const elementoPontos = document.getElementById('result-points');
    if (elementoPontos) {
        const pontos = meuResultado?.pontos_ganhos || 0;
        elementoPontos.textContent = pontos > 0 ? `+${pontos} pontos` : '0 pontos';
        elementoPontos.className = 'result-points' + (pontos === 0 ? ' zero' : '');
    }

    const elementoTempo = document.getElementById('result-time');
    if (elementoTempo) {
        if (meuResultado?.tempo_resposta_ms > 0) {
            const segundos = (meuResultado.tempo_resposta_ms / 1000).toFixed(1);
            elementoTempo.textContent = `Tempo: ${segundos}s`;
        } else {
            elementoTempo.textContent = 'Não respondeu';
        }
    }

    const listaRanking = document.getElementById('result-ranking');
    if (listaRanking) {
        listaRanking.innerHTML = '';

        dados.ranking.slice(0, 5).forEach((jogador, indice) => {
            const li = document.createElement('li');
            li.className = jogador.nome === estadoLocal.jogador?.nome ? 'self' : '';
            li.innerHTML = `
                <span>${indice + 1}. ${escaparHtml(jogador.nome)}</span>
                <span>${jogador.pontuacao} pts</span>
            `;
            listaRanking.appendChild(li);
        });
    }
}

function exibirPodio(podio) {
    podio.forEach(entrada => {
        const elemento = document.getElementById(`podium-${entrada.posicao}`);
        if (elemento) {
            elemento.querySelector('.podium-name').textContent = entrada.nome;
            elemento.querySelector('.podium-score').textContent = `${entrada.pontuacao} pts`;
        }
    });

    criarConfetes();
}

function exibirRanking(ranking) {
    const lista = document.getElementById('leaderboard-list');
    if (!lista) return;

    lista.innerHTML = '';

    ranking.forEach((jogador, indice) => {
        const li = document.createElement('li');
        li.className = jogador.nome === estadoLocal.jogador?.nome ? 'self' : '';
        li.style.animationDelay = `${indice * 0.1}s`;
        li.innerHTML = `
            <span class="position">${jogador.posicao}</span>
            <span class="name">${escaparHtml(jogador.nome)}</span>
            <span class="score">${jogador.pontuacao} pts</span>
        `;
        lista.appendChild(li);
    });
}

function criarConfetes() {
    const container = document.getElementById('confetti');
    if (!container) return;

    container.innerHTML = '';

    const cores = ['#E21B3C', '#1368CE', '#D89E00', '#26890C', '#6C5CE7', '#00CEC9'];
    const quantidade = 100;

    for (let i = 0; i < quantidade; i++) {
        const confete = document.createElement('div');
        confete.className = 'confetti';
        confete.style.left = Math.random() * 100 + '%';
        confete.style.backgroundColor = cores[Math.floor(Math.random() * cores.length)];
        confete.style.animationDuration = (Math.random() * 2 + 2) + 's';
        confete.style.animationDelay = Math.random() * 3 + 's';
        container.appendChild(confete);
    }

    setTimeout(() => {
        container.innerHTML = '';
    }, 6000);
}

function mostrarSobreposicaoConexao() {
    const elemento = document.getElementById('connection-overlay');
    if (elemento) elemento.classList.remove('hidden');
}

function esconderSobreposicaoConexao() {
    const elemento = document.getElementById('connection-overlay');
    if (elemento) elemento.classList.add('hidden');
}

function mostrarErro(mensagem) {
    const elementoErro = document.getElementById('join-error');
    if (!elementoErro) return;

    elementoErro.textContent = mensagem;
    elementoErro.classList.remove('hidden');

    setTimeout(() => {
        elementoErro.classList.add('hidden');
    }, 3000);
}

function escaparHtml(texto) {
    const div = document.createElement('div');
    div.textContent = texto;
    return div.innerHTML;
}


// === HANDLERS ===

function tratarEntrada() {
    const entradaNome = document.getElementById('player-name');
    const nome = entradaNome ? entradaNome.value.trim() : '';

    if (!nome) {
        mostrarErro('Por favor, digite seu nome');
        return;
    }

    if (nome.length > 20) {
        mostrarErro('Nome muito longo (máx 20 caracteres)');
        return;
    }

    conexao.emit('entrar', { nome });
}

function tratarResposta(indice) {
    if (estadoLocal.jaRespondeu) return;

    estadoLocal.jaRespondeu = true;

    document.querySelectorAll('.option-btn').forEach((btn, i) => {
        btn.disabled = true;
        if (i === indice) {
            btn.classList.add('selected');
        }
    });

    conexao.emit('responder', {
        resposta: indice,
        timestamp: Date.now()
    });

    atualizarContagemEspera(1, estadoLocal.jogadores.length);
    mostrarTela('aguardando');
}


// === INICIALIZAÇÃO ===

document.addEventListener('DOMContentLoaded', () => {
    inicializarSocket();

    const btnEntrar = document.getElementById('btn-join');
    if (btnEntrar) {
        btnEntrar.addEventListener('click', tratarEntrada);
    }

    const entradaNome = document.getElementById('player-name');
    if (entradaNome) {
        entradaNome.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                tratarEntrada();
            }
        });
    }

    document.querySelectorAll('.option-btn').forEach((btn, indice) => {
        btn.addEventListener('click', () => tratarResposta(indice));
    });

    console.log('Trivion Cliente inicializado');
});
