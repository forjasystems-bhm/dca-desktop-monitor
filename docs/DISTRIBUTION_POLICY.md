# Política de distribuição — F19

A linha única de consolidação é a PR #23, derivada de F03
`e40aa83c6ab11cf5509e32fdfb1264c28e1aa100`. A PR #20 não é base.
Os workflows desta linha executam fontes, testes e capturas da interface real;
não criam executáveis, instaladores ou releases. `backend/distribution_policy.py`
e sua regressão bloqueiam inclusão acidental de comandos conhecidos de empacotamento.
Isso é uma barreira de regressão revisável, não um controle de acesso administrativo.

Distribuição requer autorização independente após revisão, integração definitiva,
homologação Windows e plano de recuperação com dados reais autorizado separadamente.
Nenhuma variável de ambiente libera distribuição. Uma autorização futura exige uma
alteração revisada da política e da receita de build na mesma linha canônica.

**Limite administrativo:** arquivos nesta PR não desabilitam workflows existentes
em outras branches e não impedem um administrador de publicar manualmente. Ao integrar,
o mantenedor deve arquivar as linhas antigas de distribuição, configurar rulesets e
proteger ambientes de publicação com aprovação humana. Essas ações não foram executadas.
Não há alegação de congelamento global de branches legadas.
