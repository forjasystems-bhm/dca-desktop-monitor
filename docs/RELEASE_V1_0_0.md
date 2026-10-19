# DCA Monitor 1.0.0 — candidato, ainda sem publicação oficial

Status: a publicação depende de F19 administrativa, revisão da integração e
validação dos pacotes no commit final. A existência deste documento ou de um
artefato do Actions não significa que a versão foi publicada em GitHub Releases.

A versão de produção deve ter apenas dois arquivos finais:
- DCA-Monitor-v1.0.0-Windows-x64.zip
- DCA-Monitor-v1.0.0-Linux-x64.tar.gz
com respectivas somas SHA-256 publicadas em GitHub Releases.
Cada arquivo completo contém recursos e um manifesto do commit de origem.
Não baixar apenas o executável interno nem combinar arquivos de versões distintas.

A pasta inteira do programa deve ser extraída. Windows: executar
`DCA-Monitor.exe`; Linux: executar `DCA-Monitor` após `chmod +x`.
O banco fica na pasta de dados do usuário, não na pasta substituível do
aplicativo. Nunca inserir um CSV pessoal na distribuição.

**Conciliação:** importa registros legados sem modificá-los, apresenta
diferenças por linha na ação **Conferir lançamentos** e mantém resultado
não conciliado como não apurado. Só corrige por edição explicitamente
justificada, com trilha de auditoria.
No Dashboard, use **Conferir lançamentos**, selecione a operação e abra
**Consultar / corrigir operação selecionada**. O editor exige motivo e confirmação.
Não presume que diferença seja corretagem. A conciliação de uma linha não aprova
automaticamente outras: estas continuam pendentes. Importação e uso local são
distintos de conferência e aprovação do resultado financeiro.

**BRL histórico:** utiliza taxa/câmbio da operação e base documentada.
Se câmbio, custo ou corretagem estiverem ausentes, o lucro líquido BRL
afetado fica indisponível, sem multiplicar lucro USDT por cotação atual.
Não é cálculo fiscal.

**Atualizações:** Aplicativo / Configurações → Verificar atualizações →
Baixar atualização. A transferência exige pacote do repositório oficial,
versão superior e SHA-256 GitHub. O download não executa o pacote e não
substitui automaticamente o banco. Feche o aplicativo, faça backup
verificado e só então instale a versão baixada.
**Preparar atualização (backup recuperável)** cria um pacote com SQLite,
CSV original quando houver e configurações e comprova a recuperação em pasta
temporária antes de fornecer a orientação manual. Se a preparação falhar,
preserve a versão atual. O botão **Instalar atualização** fica desabilitado:
esta versão portátil não oferece troca automática, reabertura supervisionada,
atualização automática de atalhos ou rollback automático de executáveis.
Essas capacidades não foram homologadas e não devem ser anunciadas como prontas.

Para troca manual, preserve a pasta antiga inteira; extraia a nova pasta completa
em um destino novo; encerre a versão antiga; abra a nova e confirme os mesmos dados
persistentes. Atualize o atalho explicitamente depois da conferência. Se houver
falha, não abra banco migrado com binário antigo: mantenha evidências e restaure
snapshot compatível em pasta isolada, reconciliando gravações posteriores.

**F19:** a publicação automática fica bloqueada na ausência da variável
`DCA_DISTRIBUTION_APPROVED_SHA`, coincidindo exatamente com o SHA da
tag da versão, e declaração do ambiente `production`. A declaração YAML
**não configura** revisores, proteção de tags ou ambientes no GitHub. Proteção
de branches e de todos os workflows legados precisa de configuração
administrativa independente e comprovação. O código não concede essa
proteção por si só.
As operações administrativas exatas e os testes negativos estão em
`FINALIZACAO_1_0_0_BLOQUEIOS.md`. Não usar bypass nem remover proteções para publicar.

**Assinatura:** não há certificado Authenticode. O SHA-256 publicado pelo
GitHub detecta divergências de bytes, mas não certifica juridicamente o
editor. Não ignore avisos do Windows nem contorne políticas de segurança.
