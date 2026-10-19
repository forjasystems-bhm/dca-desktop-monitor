# OPS-02 — Preparação do Windows, ainda SEM distribuição

**Não publicar, não gerar instalador, não enviar executável e não aplicar atualização nesta etapa.**

## Comportamento esperado no futuro

- A primeira instalação deve registrar o programa em uma pasta de aplicativos e manter os dados financeiros numa pasta privada do usuário, fora da pasta substituível do programa (`%LOCALAPPDATA%/DCA Desktop Monitor` por padrão).
- A criação do atalho da área de trabalho será ação separada e explícita. O nome correto do controle é **Criar atalho**, não instalar novamente. O atalho deve apontar para a versão instalada, nunca para arquivos temporários do GitHub.
- Ao detectar uma nova versão publicada e confiável, o programa deverá **informar** a atualização disponível. Não trocar arquivos em uso nem atualizar silenciosamente dados ou banco.
- Antes de qualquer troca, conferir procedência e assinatura do publicador quando houver, SHA do pacote e compatibilidade; criar/validar backup SQLite usando API de backup do SQLite, incluindo WAL.
- A versão nova deve reutilizar o mesmo diretório de dados e **nunca** instalar por cima do SQLite ou reimportar o mesmo CSV. A migração de schema exige snapshot antes.
- Se a atualização falhar, permanecer na versão anterior, com dados intocados e caminho de recuperação testado.

## Implementação de preparação

`backend/windows_lifecycle.py` faz o *preflight local* sem executar uma atualização: separação dos dados, hash de um arquivo de teste local e backup verificado antes de qualquer procedimento de troca. Um hash, por si só, **não comprova autoria digital**; assinatura digital e aprovação do usuário seguem obrigatórias para uma futura atualização confiável.

**Não existe instalador operacional nesta PR**, nem geração de `.exe`, criação automática de atalhos ou agente de atualização em segundo plano. A etapa funcional de distribuição fica reservada para depois de verificar a migração real.

## Gate de homologação antes do primeiro download

1. Submeter **cópia** de CSV real da instalação antiga. Comparar conteúdo, contagem, hash, posições, saldos e efeitos históricos do SQLite importado; conservar original intacto.
2. Simular novo usuário que já possui BTC/ETH e stablecoins em corretora/cold wallet, com e sem custo de aquisição, sem comprar nada fictício. Confirmar patrimônio de mercado, bloqueio de ROI sem dados e impossibilidade de duplicação.
3. Restaurar snapshot WAL em banco separado, validar SHA/manifesto/SQL e comparar os registros.
4. Simular troca de versão mantendo o banco em pasta independente. Confirmar que o procedimento de backup falha fechado.
5. Inspecionar a interface real do primeiro uso; aprovar terminologia de **Importar CSV**, **Cadastrar saldo existente** e **Começar vazio**.
6. Só depois, autorização explícita para construir pacote e iniciar homologação real no Windows.

**Decisão de produto pendente:** eventual arquivo CSV com lacunas históricas, taxas em outras moedas e combinações de histórico CSV com saldo fora da ferramenta precisam de conciliação específica, nunca soma automática.

**STOP**: não fazer merge na `main`; não criar release ou artefato de instalação.
