# F04 — Um lançamento por comando de custódia

Base validada: `fix/dca-f03-same-day-custody-order`,
`e40aa83c6ab11cf5509e32fdfb1264c28e1aa100`.
Escopo exclusivo: F04 da auditoria `Auditoria_DCA_Desktop_Monitor.html`.
Sem AGENTS.md ou docs/agent-protocol/ nesta base. F01, F02 e F03 preservadas.

## Falha reproduzida antes da correção

Com saldo externo fictício de 1 BTC, repetir a transferência documentada de
0,1 BTC de A para B gerava duas linhas e baixava A para 0,8 BTC. O teste
adversarial anterior à alteração falhou com `2 != 1`.

## Contrato de identidade

- Cada intenção de registrar um evento possui `comando_id`, associado aos
  dados documentais/financeiros e à justificativa do movimento.
- A mesma identidade com os mesmos dados retorna o ID já registrado, com
  `registrado_agora=False`. Não insere movimento, baixa saldo, credita receita
  ou gera outro backup. A comparação monetária usa Decimal: `0.1` e `0.100`
  representam o mesmo valor, sem reescrever os valores originais.
- A mesma identidade com outros dados é recusada e a transação é revertida.
- Eventos reais com valores, data, ativo e justificativa iguais são permitidos
  com identidades diferentes. Não há deduplicação por valores ou texto livre.
- Integrações que repetem um comando devem conservar e reenviar `comando_id`.
  Para compatibilidade, omitir a chave inicia um NOVO comando com identidade
  gerada e retornada pelo serviço; omissão não representa retry. Uma referência
  documental pode ser usada como chave se identificar univocamente o evento
  (por exemplo, documento e índice do lançamento, não só valores financeiros).
- Identidades aceitam 1 a 128 caracteres ASCII: letras, números, `.`, `_`, `:`, `-`.

A consulta de identidade e a gravação ocorrem na mesma transação
`BEGIN IMMEDIATE`; índice UNIQUE oferece uma segunda proteção no SQLite.
Uma validação recusada não reserva a identidade. O retry consulta o registro
antes de revalidar saldo ou ordenação: continua válido após consumo do saldo,
movimentos posteriores ou reabertura do aplicativo.

## Interface existente

O formulário mantém uma identidade para o comando atual. Reentrância durante
a confirmação e callbacks repetidos após sucesso não enviam outro lançamento.
Após gravar, **Registrar movimentação verificada** fica desabilitado e
**Nova movimentação** permite iniciar outro evento, inclusive com valores iguais.
Os campos são preservados para facilitar operações semelhantes. Não se pede
um identificador técnico ao usuário nem se redesenha o dashboard.

## Evolução mínima do armazenamento

Schema v6 → v7: snapshot verificado antes da evolução, coluna nullable
`movimentacoes_custodia.comando_id` e índice único para identidades não nulas.
Linhas antigas continuam com NULL: não se inventa identidade documental,
não se apagam duplicatas antigas e não se alteram custos/datas/saldos do legado.
A listagem inclui `Comando_ID`; o cálculo temporal e a ordenação F01–F03
permanecem inalterados.

Esta evolução não implementa a reforma geral de migrações/recuperação F08–F13.
Uma versão antiga do aplicativo não deve ser usada como escritora de um banco
v7: a governança completa de compatibilidade permanece no backlog F12.

## Validação

- 11 testes adversariais novos em `tests/test_f04_custody_idempotency.py`:
  transferência repetida; venda repetida após reabertura e saldo esgotado;
  eventos reais iguais; conflito; equivalência Decimal; concorrência;
  recusa sem reserva da chave; retry de evento antigo; identidade inválida;
  backup pós-COMMIT com falha; evolução preservando registros v6.
- Estado completo das tabelas comparado após recusa/retry; CSV fictício
  original conferido byte a byte. Não foi usado CSV real.
- Execução local: Python 3.12/Linux, 11 testes específicos e 202 testes totais
  aprovados. `git diff --check` e compilação dos arquivos Python sem erros.
- Smoke Windows ampliado: formulário real, callback reentrante, repetição
  após sucesso e novo evento explicitamente escolhido com valores iguais.
- CI Linux/Windows deve ser conferido no SHA da PR, incluindo os logs completos.
  Resultado verde não elimina exceções de callbacks; ocorrências F18 devem ser
  registradas no relatório do incremento, sem correção neste escopo.

## Limites e STOP

Não recupera identidade de eventos antigos, não concilia taxa/P&L (F05–F07),
não corrige threads/encerramento da GUI (F18) e não altera workflows de build.
Retry idempotente não afirma que um backup anterior com falha foi reparado;
a política de backups continua como pendência F13.

Não autoriza merge, release, instalador, atualização de executável ou uso do
CSV real. Parar após F04, apresentar commit/PR e evidências, aguardar revisão
humana antes de iniciar F05.
