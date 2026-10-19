# QA-02 — Congelamento funcional antes de testar um CSV real

**Estado:** PR #19 em rascunho. `main` não modificada. Nenhum instalador, EXE, Release ou pacote de download gerado.

## Cadeia de implementação que deve permanecer isolada
- #5 (SQLite+integração), #6 (histórico de preços), #7–#11 (integridade e resultados financeiros), #12 (UI), #13 (offline), #14 (backup), #15 (primeiro uso), #16 (saldos externos e correção), #17 (transferências/vendas e taxas externas), #18 (painel Windows), **#19 (QA)**.
- As PRs #1–#4 são documentação/abordagens anteriores, não bases da cadeia atual. Não executar merges sobrepostos sem revisão da árvore, SHA, schema, conflitos e regras já substituídas.
- Nenhuma PR foi mesclada em `main` ou marcada como pronta para lançamento sem autorização.

## Capacidades implementadas e testáveis sem CSV real
1. Dados locais SQLite; importação CSV de 7 ou 8 campos por arquivo escolhido, hash SHA-256 e confirmação; backup do original e idempotência.
2. Registrar posições anteriores fora do histórico, com custódia identificada, quantidade Decimal e custo opcional. Ausência de custo não se transforma em zero.
3. Conciliação de CSV + ativos externos por declaração de independência, com proteção contra custódia duplicada.
4. Transferência entre custódias externas e venda com receita USDT, taxa USDT e taxa cobrada **no próprio ativo**; custódia externa nunca modifica operações do CSV.
5. Teste de insuficiência de posição, taxas inválidas, data retroativa, operação duplicada, replay por data UTC, saldos e ganhos separados; correções auditadas com rollback transacional.
6. Patrimônio atual e histórico fechados sobre fontes reais; valores históricos somente com cotações persistidas; P/L desconhecido bloqueado.
7. Abertura offline, cotação invalida/desatualizada não cria patrimônio falso, tratamento de rede e encerramento.
8. Backups SQLite via API com verificação, restauração em arquivo independente e ativação offline com confirmação, backup prévio e rollback.
9. Tela Windows **Aplicativo / Configurações**: consultar releases estáveis, criar atalho apenas para instalação Windows real, bandeja opt-in com abrir/atualizar/sair e manutenção assistida.
10. Workflow de CI para Linux e Windows com **apenas testes financeiros, GUI smoke e capturas reais**. Passos de PyInstaller e download desabilitados.

## Limites conscientes antes do primeiro download
- **CSV verdadeiro:** ainda não foi conferido. Verificar byte a byte o CSV original; quantidade de registros, tipos, valores e taxas, posições por ativo, fechamentos históricos, custo médio, depósitos, USDC/USDT e erros de importação; preservar a única cópia verdadeira.
- **Taxas pagas em terceira criptomoeda:** não são simuladas por taxa em USDT/BRL nem convertidas ao câmbio de hoje. A rotina de custódia já suporta taxa paga no ativo negociado, mas terceiro token exige livro dessa moeda, momento e cotação histórica documentada. Esta limitação precisa aparecer na homologação; nenhum resultado artificial é aceitável.
- **Atualização e instalação reais:** pré-validador, painel e políticas existem; o botão de aplicar update está **desabilitado** porque NÃO há release, pacote autenticado ou executável homologado. Para testar instalador, clique/atalho real e rollback de EXE, será necessária uma etapa posterior autorizada de packaging sem dados reais, independente do merge.
- **Bandeja física:** há integração pystray e testes de controle da janela; a confirmação do ícone no systray real e da ação dupla clique será feita durante homologação manual em Windows físico.
- **Recuperação em Windows real:** as falhas injetadas são testes determinísticos; homologar manutenção sem documentos em uso e cópia externa do backup na máquina de teste antes de prometer recuperação em qualquer hardware.
- Nenhuma responsabilidade de custódia de chaves, API de execução ou negociação automática foi adicionada.

## Checklist de liberação posterior
1. CI Linux e Windows 100% PASS no exato HEAD da PR #19.
2. Conferência manual dos prints da janela real para 980×700 e resolução maior.
3. Homologação usando **cópia do CSV real** e duas instalações fictícias (usuário antigo e usuário com cold wallet).
4. Com autorização separada, consolidar/revisar PRs por cadeia, preparar pacote de homologação e testar instalação e atualização em Windows físico sem usar banco do usuário.
5. Somente após novo aceite do decisor permitir merge em `main`, build/release assinado ou versão beta para download.

**STOP:** Aprovação dos testes automatizados ≠ aprovação de dados reais, de um instalador ou de um release.
