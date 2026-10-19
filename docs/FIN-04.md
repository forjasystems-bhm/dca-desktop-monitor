# FIN-04 — USDT e USDC sem paridade contábil fictícia

Branch dependente de FIN-03 (PR #8). **Não é versão pronta para distribuição.**

## Diagnóstico confirmado no código de origem
O formulário tratava `USDC` e `USDT` como moedas de depósitos/saques, mas o motor identificava só `USDT` como saldo externo; `USDC` acabava contabilizado como compra/venda de cripto no livro de USDT, gerando distorções de caixa, patrimônio e P/L.

## Regras implantadas

1. **USDT e USDC são unidades de caixa distintas.** Transferência USDT afeta USDT; transferência USDC afeta USDC. Depósito de USDC **não financia compra em USDT**.
2. O campo legado `Valor_USDT`, nas linhas `USDC`, registra um **valor nominal em unidades USDC** compatível com o CSV original — **não uma cotação de paridade**. Requer `Quantidade = Valor_USDT` nas transferências.
3. `Preco`, para linhas de transferência de stablecoins, representa taxa BRL da moeda selecionada, informada pelo operador. `Taxa_BRL` permanece registro histórico de FX, **não taxa de corretagem**.
4. O formulário **não** preenche automaticamente USDC/BRL com USDT/BRL, e nunca assume USDC = USDT = USD. A taxa deve ser informada pelo operador quando não disponível explicitamente para USDC.
5. Transferências de USDC (compra=vinda do exterior/carteira, venda=saída) não constituem compra/venda de BTC/ETH nem lucro realizado em USDT. Nenhum P/L realizado fictício em USDC.
6. **Patrimônio atual** pode incluir USDC detido somente mediante cotação confiável **USDC/USDT**. Exemplo: 200 USDC com preço 0,965 = 193 USDT, não 200. Sem cotação, total = indisponível.
7. Mesmo com cotação atual confiável, **não é possível apurar resultado não realizado do USDC** apenas a partir de depósitos/saques; custo histórico real não consta do modelo atual. Assim, P/L não realizado e total da carteira ficam indisponíveis até evolução contábil, mas o patrimônio pode ser apresentado quando todos os preços estão disponíveis.
8. **Patrimônio histórico**: somente fechamento UTC do par USDC/USDT da data pedida, persistido em SQLite (HIST-01). Sem fechamento, total indisponível. Não usar cotação atual.
9. O painel Caixa apresenta USDT e USDC **separados**, com entradas e saídas de USDC expressas em unidades USDC. A análise por período mostra fluxos de USDC separadamente, sem somá-los a aportes, retiradas e volume negociado em USDT.
10. Saque USDC maior do que saldo gera erro com rollback; alterar ou excluir transferências que deixam o saldo negativo também é bloqueado transacionalmente.

## Limitação histórica / ambiguidade

O CSV legado não contém uma classificação inequívoca de negociação, custódia ou transferência de USDC. A regra de leitura adotada é a mesma do formulário legado: `compra` como entrada externa de unidades e `venda` como saída externa. **Se registros antigos de USDC tiverem representado conversões ou negociação**, é necessária conciliação assistida e documentação de contraparte; não é correto convertê-los automaticamente.

Este modelo **ainda não** implementa troca USDC↔USDT, P/L cambial de stablecoins, custo individual/fiscal em BRL, taxas pagas em ativos, nem inferência de taxa de câmbio com base na valorização histórica. Esses casos requerem esquema transacional e evidências adicionais em FIN-05+.

## Critérios de aceite

- Depósito 250 USDC não cria 250 USDT, e retirada de USDC não reduz caixa USDT.
- 200 USDC precificados a 0,965 USDT = 193 USDT de mercado, não 200; P/L sem custo = não apurado.
- Falta de cotação USDC/USDT impede patrimônio consolidado, mesmo com o nominal do CSV presente.
- Fechamento histórico da data impede uso da cotação atual ou 1:1, e mantém P/L indisponível sem custo.
- Entrada/saída de USDC fora de P/L realizado e volume negociado; posição encerrada dispensa cotação.
- Simulação de saque acima de saldo, exclusão de depósito e reabertura do SQLite sem perda de dados.
- Teste de interface Windows: caixa USDC separado do USDT, patrimônio com 0,965 e custos não inventados.
- Testes Ubuntu e Windows + build interno. Nenhum download, merge nem release para usuário.
