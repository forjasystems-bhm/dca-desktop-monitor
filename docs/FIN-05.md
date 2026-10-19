# FIN-05 — Taxa de corretagem, sem complicar

**Uma única taxa opcional em USDT** para cada compra ou venda de criptoativo, informada pelo usuário a partir do comprovante da corretora.

## Como funciona
- No registro e na edição, um campo **Taxa corretagem (USDT)**.
- Deixar **em branco**: taxa não informada (não inventar comissão retroativa).
- Informar **0**: taxa confirmada como zero.
- Informar valor positivo: custo de execução em USDT, considerado imediatamente no saldo e resultados.
- **Compra:** saldo USDT diminui em `valor bruto + taxa`; custo da posição sobe pelo mesmo valor.
- **Venda:** saldo USDT sobe em `valor bruto - taxa`; lucro realizado usa essa receita líquida e o custo médio da posição.
- **Histórico:** cálculos do período e avaliação histórica aplicam somente taxas que estão explicitamente registradas.
- Mensagem informa quando existem operações sem taxa documentada; não rotular resultados como lucro líquido integral.

## O que permanece separado
- `Taxa_BRL` no CSV existente é **câmbio USDT/BRL**, não corretagem.
- A nova coluna `Taxa_Corretagem_USDT` fica no **SQLite v3**, acrescentada sem regravar operações ou o arquivo CSV original. Linhas legadas têm valor **NULL**.
- Exportação CSV inclui a nova coluna sem omitir o dado, enquanto os sete campos anteriores permanecem intactos.
- USDC é saldo externo separado (FIN-04); **transferências** de USDT/USDC não aceitam esta taxa de corretagem de negociação.

## Fora do escopo desta etapa
- Taxas cobradas em BTC/ETH/BNB ou outras moedas, desconto de plataforma, rebates, comissão percentual automática ou conversões presumidas;
- Taxas de rede em transferências;
- Custo fiscal em BRL e apuração cambial realizada do próprio USDT;
- Preenchimento retroativo com taxa de 0,1% ou estimativa da corretora.

Essas situações exigem informação adicional do comprovante e terão modelo separado, em vez de inventar encargos.

## Testes
- Migração SQLite v2→v3 e preservação do CSV;
- Posição comprada com taxa, venda parcial e total com taxa, custo médio, caixa, P/L realizado e histórico;
- Recusa de taxa negativa/NaN, taxa acima da receita da venda, compra sem saldo após contabilizar taxa;
- Diferença entre `NULL` e `0`, edição com rollback, exportação/importação;
- Windows GUI com campo opcional real e verificação do custo da posição.

**STOP:** PR dependente de #9, sem merge na main e sem novo download para o usuário.
