# DCA Monitor 1.0.0 — entregas Windows e Linux

A versão de produção deve ter apenas dois arquivos finais:
- DCA-Monitor-v1.0.0-Windows-x64.zip
- DCA-Monitor-v1.0.0-Linux-x64.tar.gz
com respectivas somas SHA-256 publicadas em GitHub Releases.

A pasta inteira do programa deve ser extraída. Windows: executar
`DCA-Monitor.exe`; Linux: executar `DCA-Monitor` após `chmod +x`.
O banco fica na pasta de dados do usuário, não na pasta substituível do
aplicativo. Nunca inserir um CSV pessoal na distribuição.

**Conciliação:** importa registros legados sem modificá-los, apresenta
diferenças por linha na ação **Conferir lançamentos** e mantém resultado
não conciliado como não apurado. Só corrige por edição explicitamente
justificada, com trilha de auditoria.

**BRL histórico:** utiliza taxa/câmbio da operação e base documentada.
Se câmbio, custo ou corretagem estiverem ausentes, o lucro líquido BRL
afetado fica indisponível, sem multiplicar lucro USDT por cotação atual.
Não é cálculo fiscal.

**Atualizações:** Aplicativo / Configurações → Verificar atualizações →
Baixar atualização. A transferência exige pacote do repositório oficial,
versão superior e SHA-256 GitHub. O download não executa o pacote e não
substitui automaticamente o banco. Feche o aplicativo, faça backup
verificado e só então instale a versão baixada.

**F19:** a publicação automática fica bloqueada na ausência da variável
`DCA_DISTRIBUTION_APPROVED_SHA`, coincidindo exatamente com o SHA da
tag `v1.0.0`, e revisão do ambiente protegido `production`. Proteção
de branches e de todos os workflows legados precisa de configuração
administrativa independente e comprovação. O código não concede essa
proteção por si só.

**Assinatura:** não há certificado Authenticode. O SHA-256 publicado pelo
GitHub detecta divergências de bytes, mas não certifica juridicamente o
editor. Não ignore avisos do Windows nem contorne políticas de segurança.
