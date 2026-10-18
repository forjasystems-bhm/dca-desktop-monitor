# HIST-01 — Cotações históricas verificáveis e patrimônio em uma data

**Situação:** proposta de implementação, ainda sem autorização de merge/release. Base: `integration/financial-data01` (PR #5).

## Regra inviolável

**Proibido calcular patrimônio retrospectivo usando a cotação atual.** Na falta do fechamento histórico do ativo detido na data, mostrar *INDISPONÍVEL* no patrimônio consolidado e no resultado não realizado; o resultado **realizado** continua disponível pelas operações.

## Definição do recorte

- Moeda de referência **USDT**, não BRL. Não há conversão histórica BRL nesta etapa.
- A data **AAAA-MM-DD** significa: operações do CSV/SQLite cuja **data civil registrada** seja <= data escolhida, somadas à cotação **de fechamento diário UTC dessa data**.
- O CSV antigo possui data/hora **sem fuso horário**. Não é possível reconstruir o timezone efetivo da operação; a aplicação não presume uma conversão artificial.
- A fonte de preço para o fechamento é a **Binance** via `ccxt.fetch_ohlcv('ATIVO/USDT', timeframe='1d', since=00:00 UTC, limit=1)`; exige timestamp do início do candle idêntico ao da data desejada e dia **completamente encerrado** em UTC. Não usa o `ticker.last` da Binance.
- Não interpola dias sem negociação, nem recua automaticamente até o último fechamento, nem inventa preço para criptomoedas sem par. Sinaliza insuficiência.
- As cotações são armazenadas em `cotacoes_historicas`, com data UTC, ativo, moeda de cotação, preço decimal textual, fonte, timestamp de abertura UTC e instante de captura.
- O banco guarda **uma cotação por par e dia**; retransmitir o mesmo candle é idempotente, mas divergências de preço/origem não são sobrescritas silenciosamente.
- A interface possui dois comandos diferentes:
  - **Avaliar (somente banco)**: sem consulta à internet, usa exclusivamente operações e preços já salvos no SQLite.
  - **Buscar fechamentos na Binance**: explícito e opcional, busca apenas cotações inexistentes, fora da thread Tkinter; o lote só é persistido se todas as respostas forem válidas.
- Uma posição **zerada** não exige preço da data, mas mantém todo lucro/prejuízo realizado.
- A posição aberta com cotação histórica é avaliada como `quantidade_detida_na_data × fechamento_historico_na_data`.
- O saldo em USDT é reconstruído apenas com os movimentos lançados até a data; se ficar negativo, o patrimônio completo fica *indisponível* até conciliação. Aportes USDT não são duplicados como compras de ativos.
- Histórico sem cotação: apenas *lucro realizado* e *custo contábil* permanecem calculáveis, não o valor de mercado e P/L não realizado.
- Sem taxa/comissão verificável no CSV legado, o resultado segue sem taxas; nenhuma taxa fictícia retroativa.
- Alterar registros originais influencia recálculos históricos; a futura trilha auditável de edição permanece pendente.

## Escopo técnico

- `backend/historical_prices.py`: provedor diário, validação de timezone/fechamento e recuperação sob demanda.
- `backend/storage_sqlite.py`: tabela de cotações, persistência transacional e somente-leitura histórica; versão do schema 2.
- `backend/historical_valuation.py`: reconstrução posicional/caixa e marcação a mercado estritamente histórica.
- `gui/janela_analise_periodo.py`: controles explícitos para escolher data, avaliar do banco e buscar fontes.
- `tests/test_hist01_historical.py`: regressões com Binance falsa, sem dependência de internet.
- `tests/windows_gui_smoke.py`: janela real Windows, cotação de hoje simulada diferente da histórica, verificação de valores e caso indisponível.

## Fora do escopo HIST-01

- Série diária completa/gráficos históricos de performance.
- Conversão USD/BRL histórica, incluindo datas de aquisição.
- Cotações intradiárias, fechamento de outra exchange ou preços sintéticos.
- Custódia/ordens, integração Binance de movimentações, contabilidade fiscal.
- Operações financeiras com taxas em diferentes criptoativos; requer extensão do esquema.
- Correções gerais de segurança, UX e instalação, incluindo botões de atualização/atalho/bandeja da PR #3.

## Cenários de aceite

1. Data com ativo aberto e fechamento armazenado: resultado exato com valor em USDT.
2. Data com ativo aberto e fechamento ausente: patrimônio consolidado = **indisponível** (não zero, não estimativa), realizado continua visível.
3. Posição zerada: não exige cotação, mantém P/L realizado.
4. Reabertura: cotações históricas persistidas, sem mudar o CSV original.
5. Candle errado, não encerrado, negativo ou inválido: bloqueado sem gravação parcial.
6. Consulta offline ao banco: nenhum acesso a API, independentemente de cotação atual.
7. Aplicação Windows com janela real montada e números verificados automaticamente.

**STOP:** não publicar ao usuário uma nova demo isolada; aguardar integração integral, correções restantes e homologação interna antes de solicitar avaliação.
