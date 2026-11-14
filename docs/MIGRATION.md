# Migração da base inicial

1. Faça backup e teste restauração. Faça a migração em uma cópia primeiro.
2. Pare a versão antiga, confira a tabela `users` (id, name, email, password_hash) e configure `DATABASE_URL` para o banco correto.
3. Instale `requirements.lock`, configure SMTP e gere um novo JWT_SECRET.
4. Execute `alembic upgrade head`. A revisão inicial cria tabelas `finance_*`, `login_*` e `rate_buckets`. Preserva `users` existente e não toca nas tabelas antigas `expenses` e `reports`.
5. Contas existentes podem usar sua senha armazenada por pwdlib; todas precisam passar pela etapa de e-mail. Tokens antigos não têm claims/sessão da versão nova e deixam de funcionar.
6. Confira login, criação de lançamento, orçamento e relatório na cópia antes de trocar o serviço real.

O JSON legado mistura categorias livres e possivelmente renda, gastos e objetivos. **Não há importação automática**: adivinhar a semântica duplicaria despesas ou fabricaria valores. As linhas antigas permanecem preservadas, mas não aparecem na UI nova. Para importar, estabeleça um mapeamento explícito de cada chave, confirme datas e unidades monetárias, converta com Decimal para centavos, use UUIDs determinísticos por registro e valide os totais antes/depois. Isso exige conhecer os dados reais; não use exemplos como migração universal.

As rotas mudaram. `/users/{id}`, `/expenses`, `/reports/{expenses_id}` e `/ai/chat` foram substituídas por `/auth/me`, `/entries`, `/reports/weekly` e `/reports/weekly/insights`. O login agora retorna `challenge_id`; `/auth/verify` retorna `access_token` (corrigindo a grafia anterior `acess_token`) e `refresh_token`. Toda requisição autenticada inclui `X-Device-ID` e `Authorization: Bearer ...`.

Não execute `alembic stamp` para simular migração e não apague tabelas antigas antes de conferir o backup. Downgrade destrutivo foi deliberadamente bloqueado; restaure uma cópia verificada para reverter. Novas mudanças de esquema devem criar revisões Alembic adicionais.
