# DESK-01 — Controles Windows antes de homologar o CSV real

**Base:** CUST-01, PR #17. **Entregue como código em PR draft**, sem pacote para download.

## Configurações do aplicativo
Botão **Aplicativo / Configurações** na barra inferior abre janela própria. Não acrescenta abas espremidas ao Dashboard aprovado.

### Atualizações
- Botão **Verificar atualizações**: consulta em thread separada APENAS `GitHub Releases/latest` estável do repositório oficial, nunca commit, branch, PR ou preview.
- Diferencia versão estável disponível, nenhuma release publicada, versão atual, resposta inválida e falha de rede. Offline **não** significa atualizado.
- Versões com `draft` ou `prerelease` não são aceitas; versão `vMAJOR.MINOR.PATCH`.
- Botão **Atualizar agora** permanece desabilitado até existir pacote legítimo do editor, manifesto autenticado, procedimento de upgrade comprovado e confirmação do usuário. **Nenhum download ou instalação ocorre aqui**. SHA sem assinatura não comprova procedência.
- Versão `0.0.0` atualmente designa build de desenvolvimento, não versão estável numerada/publicada.

### Atalho
- **Criar atalho na Área de Trabalho** habilitado somente em um aplicativo Windows empacotado que **não** esteja em modo PREVIEW.
- Resolve Desktop Windows com API do sistema, incluindo pasta redirecionada para OneDrive. Não cria automaticamente nem sobrescreve atalho existente. Distingue resultado `criado` de `já existe`.
- Um preview ou execução de código-fonte não pode anunciar instalação ou criar um link para pacote temporário.

### Segundo plano
- **Ao fechar, minimizar para a bandeja**: OFF por padrão, armazenado em JSON atômico na pasta de dados do usuário.
- Quando habilitado, permite **Abrir**, **Atualizar cotações** e **Sair completamente** no menu do ícone Windows. Sair cancela timers, encerra o ícone e destrói a janela; minimizar não é serviço Windows nem negociação automática.
- Bibliotecas `pystray` e `Pillow` utilizadas apenas quando necessário. Falha na bandeja **não oculta** a janela nem destrói dados.
- Nunca inicia com Windows automaticamente. Preferência danificada não habilita segundo plano silenciosamente.

### Manutenção e recuperação
- **Conferir backups**: verifica cada manifesto e SQLite `integrity_check`, exibe quantidades e erros; recomenda cópia externa.
- **Preparar cópia de recuperação**: seleciona manifesto de backup e destino independente, verifica novamente SHA-256 e integridade; proíbe sobrescrever banco operacional.
- **Fechar aplicativo e ativar recuperação**: o programa inicia **outro processo**, pede confirmação, fecha a GUI principal e oferece segunda confirmação na manutenção offline. Não executa a troca em um SQLite aberto. A execução recusa WAL/SHM/journal e bloqueio, gera snapshot antes da troca e preserva uma cópia com nome `.rollback-...`.
- Falhas não são mascaradas como recuperação concluída. O mecanismo **não** fica exposto em modo automático no primeiro boot.

## Taxas: política conservadora de primeira versão
- Operações do CSV: comissão explícita `Taxa_Corretagem_USDT`; o CSV antigo de 7 colunas permanece intacto, ausência de taxa `NULL` é desconhecida.
- Movimentos externos CUST-01: comissão explícita em USDT **e/ou** taxas deduzidas no próprio ativo (BTC, ETH etc.), com quantidade de rede registrada e baixa da posição sob teste de saldo. Registro de taxa igual a zero precisa ser informação expressa, não dedução do programa.
- Taxas em **terceira criptomoeda** (ex.: comissão em BNB por venda de BTC) no CSV não são convertidas com cotação atual nem presumidas. Exigem movimento comprovado, saldo da moeda do pagamento e cotação histórica documentada: **limitação explícita** e critério da homologação, nunca resultado falsificado.

## Critérios Windows
- Teste Linux + Windows financeiro e de SQL; smoke GUI de janela real, defaults, preferências, consulta/backup; capturas de configurações e movimentação externa.
- Conexão Binance indisponível permite consultar histórico local. Botões críticos não realizam ações de rede sem decisão.
- Não foi construído nem distribuído instalador, EXE, assinatura, Release ou pacote de atualização nesta PR.
- O próximo gate é **consolidação de QA e homologação com cópia do CSV real**. Merge e release continuam atos independentes e exigem autorização.
