# Consolidação F04–F19 — relatório técnico de implementação

## Executivo

Linha única: PR #23, baseada exclusivamente em F03
`e40aa83c6ab11cf5509e32fdfb1264c28e1aa100`. F01–F03 permanecem cobertas
por suas regressões. Não houve merge, dados reais, instalador ou release.

As correções mantêm o modelo financeiro existente, sem inventar aquisições,
depósitos, custos ou câmbio. Valores desconhecidos continuam desconhecidos.
O CSV importado permanece imutável; recuperação portátil copia e confere seus
bytes e altera somente os caminhos de proveniência na cópia recuperada.

Este documento descreve a implementação. O resultado final de CI e os SHAs
publicados ficam no relatório da PR #23: sucesso de workflow, isoladamente,
não encerra homologação operacional.

## Matriz técnica

| ID | Implementação e evidência específica | Dependência / limite |
|---|---|---|
| F04 | `storage_sqlite.registrar_movimento_custodia`: identidade `comando_id`, UNIQUE e comparação documental na transação. `test_f04_custody_idempotency.py` e smoke da GUI. | Retry deve reenviar identidade; novo comando legítimo pode repetir todos os valores. |
| F05 | `backend.py` inclui custo da taxa de rede no resultado atual; `custody_ledger.py` e histórico conciliam. `test_f05_f07_financial_consolidation.py`. | Taxa sem base comprovada permanece não apurada. |
| F06 | Resultado realizado externo desconhecido propaga `None`; subtotal CSV fica explícito. GUI trata valores ausentes. Mesma regressão financeira. | Não é lucro zero nem total completo. |
| F07 | Resultado externo por ativo, acumulado e período; corte cronológico preservado e histórico sem dupla contagem. Mesma regressão e suíte integrada. | F01–F03 são pré-requisitos. |
| F08 | Marcador persistente de identidade e rastros de uso bloqueiam criação de banco substituto vazio. `test_recovery_hardening.py`. | Perda de toda a pasta local exige recuperar pacote externo. |
| F09 | `recover.pyw`, manutenção offline sob trava, banco ausente/corrompido aceito; original corrompido preservado para rollback. Testes de desastre e de falha durante troca. | Sidecars WAL/SHM ainda presentes bloqueiam troca; não são apagados automaticamente. |
| F10 | `database_identity.py`: estrutura DCA, versão, integrity_check e UUID da carteira. Rejeita SQLite de outro aplicativo/carteira antes de substituir. | UUID identifica carteira, não é assinatura criptográfica contra adulteração deliberada. |
| F11 | `recovery_bundle.py`: ZIP com SQLite consistente, CSV original por hash, configurações e recibo. Recupera somente em pasta nova; funciona sem hard links e preserva destino concorrente. Testes de perda de caminhos e ZIP malicioso. | Destino externo deve ser reescolhido na máquina nova; pacote não carrega caminhos antigos de backup. Pacote não é criptografado. |
| F12 | Schema versionado 10, recusa futuro/danificado antes de DDL; migração transacional com snapshot anterior. Teste de falha injetada e rollback de DDL. Recuperação migra cópias identificadas v8/v9. | Backup anterior à identidade v8 não permite comprovar automaticamente a carteira: requer conferência assistida, sem atribuição silenciosa de UUID. |
| F13 | Snapshot após CRUD/cotações e demais gravações protegidas; opção explícita de destino externo com pacote portátil. Retenção de todas as cópias. Testes de espelhamento e disco cheio. | Não comprova separação física dos discos; usuário escolhe destino. Sem poda destrutiva. Monitorar espaço. Falha após COMMIT gera aviso, não falso rollback. |
| F14 | `versoes_resultados`: versão emitida imutável com regras, insumos exatos, saída e hash; cálculo usa snapshot SQLite consistente. Entrada antiga de custo passa pela correção auditada. `test_result_versions.py`. | Reexpressão atual foi preservada. Política fiscal/contábil de retificação continua decisão humana. Versões nunca emitidas antes desta correção não podem ser reconstruídas como prova pretérita. |
| F15 | `auditoria_operacoes`: antes/depois, ID, operador local, UTC, motivo obrigatório, triggers contra UPDATE/DELETE; mesma transação financeira. `test_operation_audit.py`. | Operador é conta do SO, não identidade autenticada. Não é trilha inviolável contra administrador SQLite. |
| F16 | `config/carregar_json.py`: configuração mutável persistente por usuário, gravação atômica; pacote fornece defaults/migração inicial. `test_persistent_configuration.py`. | Validar pasta de usuário/permissões no Windows de homologação. |
| F17 | Editor carrega registro preciso original e mantém texto Decimal, sem arredondar FX para duas casas. `test_edit_precision.py`. | Formatação de exibição continua distinta dos valores de escrituração. |
| F18 | `ui_dispatch.py`: workers escrevem em Queue; apenas thread principal chama Tk, tarefas por tela serializadas, callbacks descartados após destroy do widget real (sem proxy do canvas). `test_ui_dispatch.py`. Scripts GUI tornam exceções assíncronas falhas de CI. | Rede em execução é daemon; encerramento descarta resultados, não força interrupção de biblioteca de terceiros. Exige validação Windows real. |
| F19 | Uma branch/PR de consolidação; workflows de fonte sem build, regressão detecta receitas conhecidas de empacotamento. `DISTRIBUTION_POLICY.md`, `test_distribution_policy.py`. | **Parcial administrativo:** proteção global, arquivamento de workflows legados e ambiente de publicação exigem mantenedor. Nenhuma mudança em main ou outras branches. |

## Validação e evidências

Comando local: `python -m unittest discover -s tests` — 228 testes aprovados no
marco anterior à documentação; `python -m compileall -q backend gui tests main.pyw`
e `git diff --check` também executados. O total final e os links de Linux/Windows
serão registrados na PR após o marco integrado.

Adversariais incluem: identidade repetida com payload conflitante; operações
legítimas iguais; base desconhecida; rede sem base; períodos externos; desaparecimento
e corrupção do banco; backup alheio; perda do caminho CSV; ZIP com traversal;
schema futuro; DDL interrompido; auditoria imutável; precisão decimal; disco cheio;
callback após fechamento. As advertências de rejeição financeira nesses testes
são esperadas; traceback de GUI ou erro de thread não é aceito como sucesso.

## Homologação pendente de autorização

1. Revisar commits e relatório final da PR, especialmente migrações e recuperação.
2. Em Windows representativo, usar apenas cópia sintética: fechar durante consultas,
   múltiplas atualizações, edição, bandeja, reinício offline, perda/corrupção e restauração.
3. Conferir visual, Decimal, custo desconhecido, totais/parciais e versões históricas.
4. Após autorização independente, ensaiar cópia protegida dos dados reais e conferir
   bytes do CSV, relatórios e recuperação em máquina limpa. Não importar automaticamente
   backups antigos sem identidade comprovada.
5. Só então autorizar integração definitiva e, separadamente, distribuição e seus
   controles administrativos. Nenhuma dessas etapas foi executada por esta alteração.
