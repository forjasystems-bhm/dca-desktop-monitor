# FIN-02 — Cotações atuais ausentes, inválidas ou desatualizadas

**Escopo:** corrigir a confiabilidade do Dashboard atual. Esta mudança não altera cálculo de período nem cotações HIST-01, que continuam exclusivamente históricas.

## Invariantes financeiros

1. **Cotação de mercado ausente não é cotação igual a zero.** Ativo com posição aberta permanece visível, com quantidade e custo contábil preservados.
2. **Sem preço válido para qualquer posição aberta:** valor atual daquela posição, P/L não realizado e P/L total do ativo são `None` (*Indisponível*). O lucro realizado permanece calculável com as transações.
3. **Patrimônio consolidado e P/L total:** ficam *Indisponíveis* quando qualquer posição aberta não pode ser avaliada. Não somar apenas os ativos precificados como se fossem a carteira total.
4. **Distribuição percentual:** também fica indisponível com qualquer posição aberta sem cotação; nenhum gráfico de distribuição parcial aparece como completo.
5. **Posição encerrada:** seu valor presente é zero, seu P/L não realizado é zero, e o P/L realizado continua preservado. Não depende de cotação de mercado.
6. **Preço inválido:** zero, negativo, nulo, infinito e NaN são equivalentes a ausência de cotação para fins de avaliação atual.
7. **Cache da Binance:** manter em memória para diagnóstico não autoriza reutilizá-lo para avaliar a carteira depois de falha de consulta. Preços com mais de 180 segundos também são inelegíveis. O retorno posterior de uma cotação válida torna a posição avaliável novamente.
8. **USDT/BRL:** se faltar cotação atual confiável, exibir `BRL indisponível` na conversão da interface. Nunca disfarçar USD/USDT como BRL.
9. **HIST-01:** nunca utilizar cache de preço atual para apurar patrimônio de datas passadas; esse módulo continua consultando apenas `cotacoes_historicas` persistidas.

## Contrato de interface

- Cartões *Patrimônio*, *P/L não realizado*, *P/L total*, percentuais e distribuição deixam claro quando o valor é indisponível.
- *Capital aplicado*, *Compras históricas* e *Lucro realizado* permanecem visíveis e não recebem valores fictícios.
- A tabela mantém cada ativo e mostra *Indisponível* apenas onde não é possível calcular.
- Dashboard informa quais moedas estão sem cotação.
- **A versão nesta PR ainda não corrige o conceito de rentabilidade consolidada**, que será revisado em FIN-06; apenas impede calcular percentuais sobre informação de mercado incompleta.

## Validação

- `tests/test_fin02_quotes.py`: casos de cotação ausente, cache expirado, falha online/offline, valor inválido, posição zerada, patrimônio/donuts incompletos e recuperação.
- `tests/windows_gui_smoke.py`: montagem da janela Windows com valores fictícios, omissão intencional de cotação ETH, verificação de textos `Indisponível` e restauração depois de cotação válida.
- Testes de regressão das PRs #1, #2, #4 e #6 preservados.
- Nenhuma publicação, merge ou download de teste para o usuário nesta etapa.

**Dependência:** PR #6 (HIST-01), que depende da PR #5 (integração) — `main` permanece intocada.
