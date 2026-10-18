# FIN-06 — Auditoria dos indicadores e da rentabilidade

**Base:** PR #10 (FIN-05), após as PRs #5 a #9. Sem merge na branch principal.

## Definições financeiras

- **Patrimônio atual:** caixa USDT + valor de mercado de todas as posições + USDC a preço USDC/USDT comprovado. Se faltar qualquer cotação, não há patrimônio completo.
- **P/L realizado:** valores brutos de vendas menos comissão USDT documentada e o custo médio histórico das quantidades alienadas. Não depende de cotação atual. Posições encerradas continuam no histórico.
- **P/L não realizado:** valor das posições abertas ao preço atual confirmado menos custo contábil de aquisição (taxas documentadas incluídas). Na falta de cotação, indisponível.
- **P/L contábil acumulado:** P/L realizado + não realizado. **Não equivale automaticamente a resultado fiscal em BRL.**
- **Compras históricas:** giro bruto de compras de ativos, nunca os aportes do investidor. Não é denominador de ROI.
- **Aportes e retiradas externas USDT:** depósitos e saques registrados no CSV/SQLite; compras/vendas internas não são fluxos externos.
- **Resultado patrimonial auditado (USDT):** patrimônio atual menos aportes líquidos externos (`P - (aportes - retiradas)`). Deve conciliar com o P/L contábil conhecido, dentro de tolerância de arredondamento.
- **Variação da posição aberta:** P/L não realizado / custo das posições abertas. *Não é retorno total da carteira.*
- **Retorno estimado da carteira:** percentual de **Modified Dietz** ajustado pelo peso temporal diário dos aportes e retiradas externos. Formulação desde o início do livro: `(Patrimônio - Σfluxos) / Σ[fluxo × dias_restantes / dias_totais]`. Aproximação, não TWR/XIRR nem taxa anualizada.

## Bloqueios que protegem a informação

Não calcular o percentual Dietz quando:
- há cotação atual ausente ou inválida, ou resultado consolidado incompleto;
- qualquer transferência USDC exige origem/custo real ainda não classificado;
- o livro histórico é inconsistente (fundos não registrados ou venda sem posição);
- há compra/venda sem corretagem explicitamente documentada (NULL ≠ taxa zero);
- os valores de patrimônio, P/L realizado e P/L não realizado não conciliam;
- não há aportes válidos, o capital ponderado não é positivo ou não transcorreu um dia;
- existem operações futuras relativamente à data de avaliação.

Quando há taxas ausentes, conservar valores calculáveis de custo e P/L *conhecido*, mas nunca anunciar que representam resultado líquido integral.

## BRL: não confundir câmbio atual com lucro histórico

O CSV registra **Taxa_BRL como câmbio**, mas depósito USDT não comprova que o investidor o adquiriu pagando aquele valor em BRL. Uma compra de BTC a partir de USDT também não prova realização de lucro em reais. O cálculo antigo de P/L em BRL recorria ao câmbio atual para completar bases históricas: isso foi **desativado**, não mascarado.

- Alternância para BRL só converte **valor de mercado atual** quando a cotação USDT/BRL está disponível e confiável.
- Custo de aquisição e resultados contabilizados em USDT permanecem exibidos com unidade USDT, inclusive quando o usuário alterna para BRL.
- Apuração fiscal, resultado líquido em BRL e custo de aquisição do próprio USDT dependerão de registros contábeis específicos no futuro.

## Experiência visual

Identidade escura, laranja e estrutura de abas preservadas. Cartão percentual antigo `Resultado / Compras %` vira `Retorno Dietz %`. Falta de elementos suficientes exibe **Não apurado**, com motivo. Cartão `Ganho %` vira `Variação Aberta %`.

O refinamento de tabelas cortadas, responsividade e espaçamento continua reservado à UI-01.

## Validação

Testes financeiros com depósitos antes e depois da compra, retiradas, posições zeradas, corretagem, saldos sem origem, USDC, cotação ausente, lucro incompatível e retorno no mesmo dia; teste da interface real no Windows incluindo alternância BRL que não pode converter lucro histórico.

**STOP:** nenhuma publicação/merge antes de homologação integrada.
