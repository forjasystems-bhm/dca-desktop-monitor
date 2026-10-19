# DCA Monitor — prévia portátil Windows para teste pessoal

Esta prévia **não é uma release oficial, instalador, atualização automática nem
homologação financeira**. Foi compilada a partir do candidato financeiro
`8c13295aaac2ac4bcb98ead1723e713a8ae42eb2`, com mudanças estritamente
limitadas ao processo de empacotamento e às suas validações.

## Como testar no Windows

1. Baixe o artefato `DCA-Monitor-PREVIEW-Windows-x64` da execução aprovada no GitHub Actions.
2. Extraia todo o ZIP para uma **nova pasta gravável** em Documentos ou Downloads.
3. Abra `DCA-Monitor-PREVIEW.exe`. Não mova o EXE sozinho; a pasta `_internal`
   e o marcador `DCA-PREVIEW-MODE` precisam acompanhá-lo.
4. Escolha **começar vazio** ou utilize exclusivamente dados sintéticos durante
   a primeira avaliação. Não importe seu CSV original nem a única cópia de
   qualquer arquivo financeiro real.
5. A carteira dessa prévia fica somente em `preview-data` junto ao executável.
   Não altere, sobrescreva ou restaure a instalação antiga.
6. Teste início, telas, cadastros sintéticos, saldos, custos desconhecidos,
   movimentações, encerramento, reabertura, backups e restauração em pasta nova.
7. Compare os cálculos com as evidências de homologação; comunique divergência
   antes de confiar em qualquer resultado.

**Segurança:** o arquivo está sem assinatura Authenticode e o Windows poderá
mostrar alerta de editor desconhecido. Confira o SHA-256 em `SHA256SUMS.txt`,
obtido da mesma execução GitHub Actions. Não trate um alerta como prova de que
o programa é seguro, nem desative políticas de segurança do computador.

**Limite F19:** controles administrativos de publicação e linhas antigas de
distribuição continuam pendentes. Nenhuma release pública foi criada.

O aplicativo não transmite chaves privadas ou seeds para testar custódia; não
informe essas credenciais em nenhum lugar da prévia.
