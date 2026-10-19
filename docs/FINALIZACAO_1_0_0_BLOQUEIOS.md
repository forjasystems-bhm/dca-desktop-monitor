# Finalização 1.0.0 — evidências e portões administrativos

## Executivo

Referência inicial confirmada: PR #26, branch
`feature/dca-release-financial-review-and-updates`, SHA
`a6a00e07779fc84fe177cef6e36503a1b9518529`. main remota:
`62386aab7b4d2842b9bf6c247a347c7478beaca5`. Não foi usada a PR #20 como base.
Não há AGENTS.md nem docs/agent-protocol/ na árvore inicial examinada.

O objetivo é release permanente, não outra prévia. O trabalho presente não
declara publicação: F19 administrativa permanece um impedimento real. Nenhum
merge, tag ou release foi executado. Nenhum arquivo financeiro real foi utilizado.
Há ainda uma limitação funcional explícita: atualização automática de executáveis
e seu rollback não são suportados nesta versão portátil. O controle de instalação
fica desabilitado; download e preparação com backup são capacidades diferentes.

## Evidências técnicas e histórico

Baseline local: 254 testes aprovados. No mesmo SHA inicial, CI de pacotes
39266167064 aprovou Windows/Linux e inicialização de executável; os logs foram
consultados. O smoke anterior terminava processos à força e não comprovava saída
normal, reabertura ou execução após extração do arquivo definitivo. Essas provas
foram adicionadas e devem passar no novo HEAD antes de qualquer integração.

O candidato inicial contém 275 commits além de main (zero atrás); a cadeia inclui
F01 `8670710`, F02 `d4c809c`, F03 `e40aa83`, PR #23 até `5e90755`, PR #24
até `8c13295`, preparação posterior até `1fab825` e PR #26. Preservar os commits
e referências; não mesclar PRs ancestrais sobrepostas por automatismo. A árvore
integrada exige execução completa das mesmas validações em seu próprio SHA.

Revisão adicional reproduziu o caso UNI sintético: a apuração USDT apresentava
174,30 como resultado conhecido antes da conciliação de 0,50. Agora o ativo afetado,
sua base e o consolidado permanecem indisponíveis; BTC independente mantém 50 USDT.
A correção explícita de UNI de 1737,50 para 1738,00 preserva CSV, valores anteriores,
justificativa, operador e UTC. Outra divergência legada pode permanecer pendente,
mas a nova linha corrigida passa pela validação integral, assim como os saldos
temporais de todo o livro. Tolerâncias não foram ampliadas.

BRL independente: compra 2 BTC por 200 USDT, taxa documentada 2 e câmbio 5 produz
custo de 1010 BRL. Venda de 1 BTC por 150, taxa 1 e câmbio 6 resulta em
(150−1)×6−505 = **389 BRL**. Com câmbio de venda 3, resulta em **−58 BRL**.
Sem câmbio de compra, resultado permanece desconhecido. Custódia externa sem
escrituração BRL documentada permanece não apurável; não se atribui câmbio atual.

Regressões adicionais: `test_final_reconciliation.py`, `test_final_update_safety.py`
e `test_release_archive.py`. Downloads testam sucesso, adulteração, interrupção,
redirecionamento indevido, arquivo já existente, sistema/arquitetura e downgrade.
Preparação da atualização revalida bytes e prova recuperação portátil antes de
orientar uma instalação manual; testes de falha preservam SQLite e download.
Não há alegação de instalação ou rollback automático aprovados.

O empacotamento passa a testar o ZIP/TAR já fechado, extraído em pasta nova, com
manifesto de todos os arquivos e commit exato. São duas aberturas reais de GUI,
Tcl/Tk disponíveis, saída normal e preservação de SQLite com Decimal extenso e
configuração. Qualquer encerramento forçado é falha, nunca recibo de sucesso.
Os pacotes não contêm CSV, SQLite, fixtures ou marcador de prévia. Linux usa Xvfb:
isso prova a GUI em display virtual do runner, não todas as distribuições gráficas.

Clássica foi consultado em `scripts/update_app.ps1` e
`scripts/windows_clean_install.ps1`. Seus princípios de staging, confirmação de
readiness, preservação de perfil e retorno foram considerados. Copiar o helper
PowerShell seria incorreto: ele depende do servidor local, token de sessão e
launcher estável próprios daquele projeto. Não há alegação de equivalência plena
com o fluxo automático do Clássica.

## Operações administrativas faltantes — mantenedor GitHub

Constatações da conexão atual: rulesets retornaram lista vazia; leitura da proteção
de main retornou 403 Resource not accessible by integration. Ambientes e inventário
administrativo de workflows não são endpoints permitidos por esta conexão. Não se
conclui que todas as proteções possíveis estão ausentes; conclui-se que não foram
comprovadas nem podem ser configuradas por estas ferramentas.

1. **Settings → Rules → Rulesets**: criar/ativar proteção para main e linha canônica,
   exigir PR e revisão humana, descartar aprovação obsoleta, checks financeiros,
   Windows/Linux e pacotes; impedir force push e exclusão. Configurar proteção de
   tags `v*` com criação/alteração restrita aos responsáveis de distribuição.
   Não selecionar bypass para viabilizar o primeiro merge. Verificar CODEOWNERS:
   o arquivo herdado aponta para `@BRUNO1993-CIBER`; o mantenedor deve confirmar
   acesso e adequação, sem inventar um aprovador ou aprovar a própria mudança.
2. **Settings → Environments → production**: configurar revisor autorizado,
   impedir autoaprovação e bypass administrativo quando suportado, permitir somente
   tags autorizadas. Um job que não referencia esse ambiente não é protegido por
   ele: isso exige também restringir receitas antigas e mudanças em workflows.
3. **Actions → workflows legados → Disable workflow**: inventariar IDs, caminhos,
   branches/SHA e gatilhos, desabilitando receitas de distribuição fora de
   `release-packages.yml`, inclusive prévias antigas. Não apagar branches/PRs.
   Se um caminho for compartilhado com QA atual, mover a QA para caminho revisado
   antes de desabilitar a identidade antiga; não alegar bloqueio só pelo arquivo
   YAML mais novo. Não ampliar permissões globais ou entregar credenciais a PRs.
4. **Teste negativo inerte**: com ator sem autorização, comprovar recusa da mudança
   protegida, da tag não autorizada e do fluxo legado desabilitado. Usar job sem
   empacotador, credenciais ou upload para comprovar espera por revisão e recusa de
   autoaprovação. Guardar ator, SHA, configuração, recusa/run e ausência de release.
   Testes de regex/YAML locais não substituem essa comprovação administrativa.
5. Após CI final e revisão, preparar integração canônica preservando histórico;
   confirmar árvore e executar regressões e pacotes no commit integrado. Somente
   então cadastrar `DCA_DISTRIBUTION_APPROVED_SHA` no ambiente production com esse
   SHA final e criar tag correspondente. Não usar o SHA inicial por conveniência.
6. Aprovar a execução da tag no ambiente protegido. A receita verifica ancestralidade
   em main, igualdade do SHA, tag da versão, os dois jobs e checksums, recusando
   sobrescrever release existente. Conferir os dois assets permanentes, digests e
   reconhecimento do canal oficial pelo app; antes disso, esses pontos são pendentes.

Não foi executado teste administrativo negativo nesta conexão. Não foram criadas
credenciais ou permissões extras para contornar o impedimento. Resolver os itens
acima é condição necessária, mas não transforma instalação automática não
implementada em funcionalidade pronta. Aceite do escopo portátil e limites deve
ser explícito na revisão humana final.
