# OPS-01 — Aplicação desktop confiável com ou sem internet

**Base:** UI-01, PR #12. Esta etapa não inclui instalador, bandeja, atualizador nem merge.

## Invariantes de funcionamento

1. **Abrir offline:** SQLite e origem/backup são verificados primeiro. A splash **não solicita cotações**, portanto Binance offline não bloqueia acesso ao histórico.
2. **Conectar depois:** primeira tentativa de Binance é agendada em segundo plano depois da montagem da janela. Dados já existentes continuam consultáveis, inclusive Caixa, operações, análises e fechamentos históricos presentes no SQLite.
3. **Não inventar preço:** sem internet ou com ticker inválido, o preço atual e o patrimônio que depende dele ficam **Indisponíveis**. Última cotação do cache não vira cotação atual por reutilização silenciosa.
4. **Sem pedidos simultâneos:** um lock impede que atualizar múltiplas vezes, a cada timer ou clique, inicie várias consultas concorrentes à Binance.
5. **Sem callback órfão:** no encerramento, cancela timers pendentes, impede novos workers e descarta resultados de tarefas que terminem depois do fechamento. Workers já em andamento são daemon e não impedem fechar.
6. **Falha externa não apaga dados:** erro de rede atualiza a indicação de conexão e permite continuar usando o programa. Não gravar operações falsas nem substituir o arquivo SQLite.
7. **Falha dos dados locais é bloqueante:** corrupção detectada, CSV alterado depois de migrar ou backup ausente/corrompido não podem ser mascarados por uma carteira vazia. O banco e CSV são preservados e deve ser mostrado erro explícito.
8. **Backup não é recriado silenciosamente:** se a migração original consta no SQLite, a cópia de segurança deve continuar verificável. Se não estiver, interromper e solicitar recuperação do arquivo — nunca reconstruir uma cópia com a mesma origem como se nada tivesse acontecido.

## Fora de escopo

Atualização automática por versão, atalho, ícone na bandeja, instalador assinado e retomada automática de upload não fazem parte da OPS-01; nenhuma ação administrativa com dados reais foi realizada.

## Aceite

- Unit tests em Linux/Windows: abrir sem Binance, perder conexão, consultar saldos e resultados conhecidos sem cotação, reabrir SQLite, falta de backup, CSV modificado, corrupção, validação offline de compra.
- Teste de interface Windows: classe splash sem consultas de rede, trava de atualização concorrente, fechamento e nenhuma atualização após destruir a janela.
- Capturas da interface real em ambiente de QA, compilação PyInstaller interna.
- Sem alterações em `main` e sem executável parcial solicitado ao usuário.

**STOP:** requer aprovação da cadeia integrada antes de publicar.
