# FIN-03 — Escrituração financeira governada e imutabilidade do CSV original

Status: implementação em branch isolada, **dependente da PR #7** (FIN-02). Sem merge ou release.

## Regra obrigatória

Nenhuma inclusão, edição ou exclusão de operações no SQLite pode ser confirmada se deixar qualquer evento do livro cronológico com:
- saque ou compra que torne o saldo **USDT negativo**;
- venda superior à quantidade efetivamente detida do ativo naquela data;
- quantidade, preço ou `Valor_USDT` incompatíveis;
- data inválida, quantidade/valor/preço negativo, nulo ou não finito;
- alteração da moeda original em uma operação editada.

Cada alteração é simulada no **histórico completo** e, se válida, gravada **dentro da mesma transação SQLite `BEGIN IMMEDIATE`**. Caso contrário, tudo é revertido.

## Semântica precisa dos campos

- Criptoativo (BTC, ETH, etc.): `Valor_USDT ≈ Preco × Quantidade`; a tolerância técnica é limitada pelo arredondamento de até 8 casas na quantidade, pelo valor de 1 centavo USDT e por **0,01%** do valor total (o menor limite aplicável).
- `USDT` no CSV: `compra` = entrada de caixa; `venda` = retirada de caixa. `Quantidade = Valor_USDT`. **`Preco` representa a cotação USDT/BRL**, portanto NÃO se multiplica pela quantidade. O antigo nome `Taxa_BRL` também **não significa corretagem**.
- `USDC`: não inventar conversão ou saldo. Operações históricas continuam disponíveis, mas novos lançamentos/alterações envolvendo USDC ficam bloqueados até a definição de equivalência e transação na FIN-04.
- Saldo e posições são reconstituídos em `Decimal` por ordem de data/hora, com ordem original estável no empate. Valor original não é refeito/ajustado silenciosamente.
- O resultado realizado depois de uma edição válida é recalculado pelo motor histórico, nunca por cotação atual.

## Migração não destrutiva

A importação CSV **não rejeita nem reescreve** históricos antigos quando eles possuem uma inconsistência financeira preexistente; preserva bytes originais e backup da DATA-01. Um relatório de diagnóstico identifica a primeira divergência temporal. **Novas alterações em histórico legado inconsistente só poderão ser confirmadas quando o livro inteiro for reconciliado**, por exemplo com aporte retroativo verdadeiro. Não criar aportes fictícios apenas para desbloquear operações.

Esta limitação é intencional: não reconhecer saldos negativos como válidos, nem apagar automaticamente registros antigos. O assistente formal de reconciliação do legado ainda será desenvolvido.

## Interface

- Registro: remove a opção de prosseguir após aviso de saldo insuficiente.
- Registro: persiste números como strings decimais, não como floats convertidos previamente.
- Histórico/edição: mensagens específicas quando operação é recusada (venda excedente, custo/valor incompatíveis, insuficiência de fundos).
- O usuário só recebe confirmação de sucesso **depois** do `COMMIT`.

## Validações mínimas

- Saldo zero; compra sem aporte; saque acima do caixa.
- Venda total, parcial, sobreposição de compras, e venda acima do saldo.
- Editar compra antiga que financia venda futura; excluir aporte; alterar data, quantidade ou moeda; falha com rollback.
- Reconciliação entre posição aberta, P/L realizado e saldos após alterações válidas.
- SQL atomicidade e duas compras concorrentes tentando gastar a mesma reserva USDT.
- CSV legado incompleto ou inconsistente: preservação de original, bloqueio seguro de gravação e diagnóstico explícito.
- Real Windows GUI: entrada inválida recusada e registros mantidos.
- Regressões das PRs #1, #2, #4, #6 e #7.

**Pendente:** políticas completas de USDC, taxas de corretagem, reconciliação assistida e resultados fiscais — etapas FIN-04/FIN-05. Nenhuma implementação parcial deve ser anunciada como atualização pronta para o usuário.
