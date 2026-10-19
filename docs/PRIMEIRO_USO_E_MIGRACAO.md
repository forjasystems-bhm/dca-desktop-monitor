# PRIMEIRO USO — DCA Monitor (ONB-01)

**Documento de homologação, não instrução de instalação pública.** Nada será enviado para download nesta etapa.

## Três caminhos no primeiro acesso

| Perfil | Ação do programa | O que NÃO faz |
|---|---|---|
| Usuário antigo com CSV | **Escolher arquivo CSV** de qualquer pasta → **Prévia completa** → confirmar → importar transações originais para SQLite | Não apaga CSV, não preenche lacunas automaticamente, não remove linhas repetidas |
| Já tem cripto em cold wallet ou corretora, sem CSV | **Cadastrar saldo existente** por ativo/custódia: quantidade, data, custo total USDT opcional | Não inventa compras, preço médio, aportes USDT ou taxa zero |
| Sem dados ainda | **Começar vazio** e registrar compras, vendas e depósitos reais quando ocorrerem | Não importa arquivos de demonstração |

### Caso 1 — Migração integral e conservadora

1. O programa **não pode presumir onde está o CSV antigo**, nem importar um CSV empacotado na distribuição. O usuário escolhe o arquivo original.
2. A prévia valida cada linha dos sete campos clássicos (`Data, Moeda, Operacao, Valor_USDT, Preco, Quantidade, Taxa_BRL`), aceita a coluna opcional `Taxa_Corretagem_USDT`, calcula SHA-256, contagem, moedas, datas e quantidade de linhas idênticas.
3. Linhas idênticas **não são descartadas**: podem representar operações legítimas repetidas. A prevenção de duplicação é feita no nível da migração integral: uma origem importada uma vez não é importada novamente.
4. Ao confirmar, o hash ainda é verificado **nos próprios bytes que serão importados**. Se o CSV mudar depois da prévia, a importação é cancelada.
5. O SQLite só recebe os registros em uma transação de gravação; se ocorrer erro durante a importação, o processo retorna ao estado anterior.
6. O CSV original permanece intocado e é criada cópia **byte a byte**, verificada por SHA-256. O SQLite registra o hash, o caminho original, a cópia, a data e o total importado.
7. A reabertura não duplica registros; se o CSV antigo for movido, o SQLite continua com as operações. Se o CSV registrado for alterado em disco, ou sua cópia sumir, o sistema **interrompe** e informa o problema em vez de mascará-lo.
8. Históricos antigos podem não registrar aportes USDT e outras fontes de custódia. **Importar não significa inventar conciliação financeira**. O diagnóstico indica inconsistências; o sistema não as “corrige” com aportes falsos.

**Limite intencional:** CSV com colunas extras desconhecidas, dados inválidos ou codificação incompatível não será importado parcialmente. Preservar o arquivo e relatar a linha. Regras de migração adicional serão tratadas somente com amostras legítimas do arquivo.

### Caso 2 — Saldo existente em custódia

Exemplo: usuário possui **0,025 BTC numa cold wallet** antes de ter usado a ferramenta.

Preenche:

- Ativo: `BTC`; quantidade: `0.025`; local: `Cold wallet`; data do saldo: data real da posição.
- Custo total em USDT: **deixar vazio** quando não houver comprovantes confiáveis.

Resultado: o banco registra `0.025 BTC` em `posicoes_iniciais`, **zero compras criadas**; cotação atual BTC/USDT, quando verificada, determina seu valor atual. Sem cotação, valor atual indisponível. Sem custo, lucro, preço médio e rentabilidade total não são calculados.

Se o custo total real for conhecido/documentado, pode ser informado como um valor de **custo total da posição**, sem criar várias compras fictícias. Uma venda que dependesse de custo inicial desconhecido é bloqueada até sua regularização. Isso evita relatar lucro fictício.

Vários ativos e custódias podem ser declarados, mas repetir o mesmo ativo e local é rejeitado para evitar duplicação. Informar apenas rótulo de custódia (`Cold wallet`, `Exchange A`) — **jamais solicitar seed, chave privada ou senha**. Nenhuma conexão de corretora é realizada por essa etapa.

Não é permitido misturar migração completa de um CSV com saldo inicial novo sobre o mesmo banco sem processo próprio de conciliação: isso poderia contar os mesmos BTC duas vezes.

### Caso 3 — Carteira vazia

O programa abre com o SQLite vazio. O usuário começa a registrar apenas operações reais (com custo, quantidade e taxa conhecida, quando houver).

## SQLite, backups e recuperação

- Os dados ficam na pasta de dados do usuário, separada da pasta substituível do programa. A instalação e atualização não podem apagar a pasta de dados.
- Antes de alterar esquema, cria-se snapshot SQLite pelo mecanismo online do SQLite (inclui WAL).
- Ao abrir, uma cópia diária SQLite é criada/verificada, com manifesto JSON, SHA-256 e `integrity_check`. Backups existentes não são apagados automaticamente.
- Antes de atualização, um snapshot próprio deve ser validado.
- A recuperação prepara o arquivo em local **separado** e confere o hash e o SQLite, sem sobrescrever o banco ativo. A ativação exige procedimento de manutenção com aplicativo fechado, rollback e consentimento; não é automática.

**Atenção:** a exportação do CSV de operações não substitui um backup SQLite integral, pois posições iniciais, cotações históricas, parâmetros e provas de migração vivem em tabelas distintas.

## Pré-requisitos para a primeira liberação

- Dois cenários reais de testes **em cópias**, nunca usando o único arquivo original: CSV do aplicativo antigo com conferência do total de linhas e valores, e carteira nova com saldo em custódia sem compras.
- Restauração de um backup, em base separada, comprovando valores, operações, fontes e SHA-256.
- Validação de falta de internet, de CSV deslocado e de backup ausente.
- Conferir tela de primeiro acesso Windows, botões e mensagens em 980×700 ou superior.
- Depois, testar procedimento de atalhos e atualização por versão com dados separados; sem publicar download até nova autorização.

**STOP:** não mesclar em `main`, não preparar executável ou instalador para entrega e não solicitar dados privados de corretoras.
