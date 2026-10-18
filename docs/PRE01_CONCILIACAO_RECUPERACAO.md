# PRE-01 — Conciliação, correções auditadas e recuperação

**PR #16 depende da PR #15. Nenhum instalador, release, download ou merge.**

## Quando o usuário já importou um CSV, mas possui criptomoedas fora dele

1. Importar **todo o CSV** primeiro, mediante prévia, SHA-256 e confirmação. O CSV original e a cópia de segurança ficam intocados.
2. Abrir **Dados iniciais / Importar CSV**, selecionar o ativo, quantidade, data e a custódia externa. Exemplo: `BTC`, `0,2`, `Cold wallet`, `30/09/2026`.
3. Marcar explicitamente **“Este saldo é EXTERNO e NÃO consta no CSV ou em outros saldos cadastrados”**. Sem essa confirmação, a gravação é recusada.
4. A data do saldo adicional não pode anteceder a última operação importada. O sistema não tentará atribuir retroativamente uma custódia a cada negociação antiga.
5. O sistema registra `posicoes_externas` no SQLite em tabela independente, com custódia, custo total **opcional** e evidência de declaração. Não adiciona linha ao CSV, não emite operação de compra, não cria depósito USDT e não modifica lucro realizado do livro antigo.
6. No patrimônio atual soma **quantidades e valor de mercado**, somente com cotação válida. No histórico, as unidades externas aparecem apenas **a partir da data declarada**. Custo desconhecido = preço médio, resultado aberto e ROI não apurados.
7. O saldo externo **não financia novas vendas no livro de operações**, pois isso misturaria custódias e bases históricas sem comprovante. Transferências e vendas dessa custódia exigem futura rotina própria, com evidência de movimento.
8. Se houver indicação de mesma moeda e custódia já cadastrada, recusar como duplicidade. O operador deve conferir o saldo do CSV e o extrato da wallet antes de atestar independência. Nenhuma verificação automática em blockchain consegue comprovar por si só que não houve duplicidade de lançamentos no CSV.

## Corrigir quantidade ou custo declarado

O usuário informa moeda, custódia, quantidade correta, custo documentado se houver e um motivo de ao menos 8 caracteres. O botão **Corrigir saldo registrado** exige confirmação.

O programa cria snapshot SQLite verificado **antes** da mutação, reabre os dados dentro de `BEGIN IMMEDIATE`, atualiza o registro e grava **antes, depois, motivo, data UTC, origem e ID** em `ajustes_posicoes` na mesma transação. Para posições *iniciais*, o livro inteiro é revalidado, incluindo vendas; uma correção que tornaria vendas antigas impossíveis é cancelada por rollback. Depois do COMMIT, cria nova cópia e informa eventual falha de backup, sem anunciar falsamente que o registro não foi gravado.

A posição externa também possui trilha de correção. O ajuste não apaga o cadastro anterior do log. Não há exclusão silenciosa de históricos ou arquivos.

## Recuperação completa do SQLite

Há dois processos distintos:

- **Preparar**: selecionar manifesto de backup, verificar SHA-256 + `PRAGMA integrity_check`, recuperar um arquivo independente sem alterar banco ativo.
- **Ativar** (apenas manutenção offline): aplicativo fechado, confirmação explícita `RESTAURAR BANCO SQLITE COM ROLLBACK`, rejeição se existirem WAL/SHM/journal ou conexão bloqueante, novo backup do estado atual, arquivo de rollback independente, ativação e nova validação. Falha durante a troca aciona retorno ao banco anterior; nenhum backup original é sobrescrito.

**Não há botão de restauração automática na interface**, deliberadamente, para evitar troca acidental. Antes da homologação, o fluxo será exercitado com cópias e testes de falha injetada. Backups só locais ainda exigem cópia externa/externamente armazenada contra perda do dispositivo.

## OPS-02 sem distribuição

- Código de configuração do atalho Windows aponta para executável real e pasta de trabalho correta, com opção separada **Criar atalho**; não se confunde com instalar e nunca roda automaticamente no primeiro uso.
- Planejamento de atualizações compara versões `MAJOR.MINOR.PATCH`, impede downgrade/repetição, verifica hash de pacote local de teste, mantém diretório de dados fora de `versions/<versão>` e não instala pacote algum.
- Um SHA-256 isolado **não equivale a assinatura de publicador**. A homologação deve comprovar autoria/assinatura, versão, reversão, backup pré-atualização e consentimento antes de oferecer atualização.
- Preparar o instalador real e autorizar download permanece proibido nesta etapa.

## Critérios de aceite

- Teste CSV importado + BTC em cold wallet ausente do CSV: preservar número e conteúdo de registros, P/L realizado, quantidade nova e valor patrimonial.
- Origem não confirmada, custódia duplicada e data retroativa são recusadas.
- Corrigir valores inválidos ou que causem venda sem saldo faz rollback integral, sem linha falsa na auditoria.
- Restaurar cópia SQLite, testar falha durante ativação e comprovar retorno ao banco anterior.
- Testar versão crescente/decrescente, hash inválido, localização do banco fora do app e ausência de escrita na instalação.
- Testar telas reais Windows e guardar capturas fictícias.
- **Só depois** homologação com **cópia** do CSV real. `main` permanece intacta.
