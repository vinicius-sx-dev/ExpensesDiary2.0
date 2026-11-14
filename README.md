# ExpensesDiary

Diário financeiro pessoal: FastAPI + MySQL, aplicativo React Native/Expo em TypeScript e Zustand. Uma API, um banco, sem microserviços. Interface em português, valores em BRL e datas financeiras no calendário de São Paulo.

## O que mudou

- Lançamentos individuais tipados substituem a entrada arbitrária de JSON.
- 54 categorias de despesas e 4 de receitas; catálogo servido pela API.
- Orçamento mensal geral e por categoria, objetivos com valor/prazo e aportes separados.
- Relatório semanal calculado pelo servidor; retratos salvos e comentários opcionais pela Groq.
- Login com senha + código por e-mail, JWT curto, refresh rotativo e sessões revogáveis.
- Limites compartilhados por IP, instalação, conta, usuário e geração de relatório/IA.
- App com cadastro, login, 2ª etapa, diário, criação/edição/exclusão de lançamentos e orçamentos, objetivos, aportes, consulta semanal e histórico de relatórios.

Leia a [auditoria de deploy](docs/DEPLOY_AUDIT.md) e o [procedimento de produção](docs/DEPLOY.md) antes de expor a aplicação à internet.

Veja [modelo financeiro](docs/FINANCE.md), [segurança](docs/SECURITY.md) e [migração](docs/MIGRATION.md).

## 1. API local

Python 3.12 e MySQL 8.0.16+ (preferencialmente 8.4; InnoDB para locks e FKs).

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.lock
```

Crie um banco `expenses_diary` em UTF-8 e um usuário exclusivo, sem privilégios globais. Copie `.env.example` para `.env` e configure:

- `DATABASE_URL`: conexão MySQL; escape caracteres especiais da senha com URL encoding.
- `JWT_SECRET`: segredo aleatório, gerado com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `ALLOWED_HOSTS`: hostname/IP real da API, inclusive IP de rede para acesso pelo celular.
- `CORS_ORIGINS`: origens web autorizadas; apps nativos não usam CORS como controle de acesso.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: envio dos códigos por SMTP com STARTTLS obrigatório. Não há código de teste devolvido na API.
- `GROQ_API_KEY`: opcional; sem ela os relatórios numéricos continuam funcionando.

```bash
alembic upgrade head
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --no-proxy-headers
```

Swagger local: `http://localhost:8000/docs`. A aplicação não cria tabelas na inicialização. Faça backup antes da migração de uma instalação existente.

**SMTP:** depois de configurar o provedor, o remetente é alterado por `SMTP_FROM`. Trocar de provedor também exige host, credenciais e possivelmente validar o domínio/remetente. Configure uma senha de aplicativo quando o provedor exigir. O fluxo falha de forma fechada se não conseguir enviar o código.

## 2. Aplicativo

```bash
cd mobile
npm ci
# Copie .env.example para .env e configure EXPO_PUBLIC_API_URL
npx expo start
```

- Celular físico: IP LAN do computador, mesma rede e porta 8000 liberada no firewall local.
- Emulador Android: `http://10.0.2.2:8000`.
- Web de desenvolvimento: `npm run web`.
- Release: API **HTTPS** obrigatória. Não coloque chaves de API, SMTP ou JWT em variáveis `EXPO_PUBLIC_*`.

O projeto fixa Expo SDK 58 e dependências compatíveis no lockfile; não pretende usar automaticamente o SDK mais recente. Use um cliente Expo Go compatível ou um development build. Valide qualquer atualização com `npx expo install --check` e uma execução em aparelho.

Refresh token no SecureStore no Android/iOS; access token apenas em memória. Na prévia web, ambos ficam somente em memória: recarregar a página exige novo login. Nenhum dado financeiro é persistido no armazenamento do navegador.

## 3. Rotina semanal

Consulta ao vivo: `GET /reports/weekly?week_start=AAAA-MM-DD` (segunda-feira). Gravar/atualizar retrato: `POST` na mesma URL. Histórico: `GET /reports/history`.

Para gerar automaticamente a semana anterior, agende **no servidor** a execução às segundas-feiras (fuso de São Paulo):

```bash
python -m app.weekly_job
```

O job é idempotente, processa usuários em lotes e não envia e-mails nem dados à IA. Retratos existentes são preservados. O usuário pode recalcular e gravar a semana pelo app. Configure também `python -m app.maintenance` diariamente para remover metadados de autenticação e limites expirados. O agendamento não é criado automaticamente neste repositório; use cron ou Agendador de Tarefas do servidor.

## 4. Verificação

```bash
python -m pytest -q
cd mobile
npm run typecheck
node --experimental-strip-types --test tests/*.test.mjs
npx expo install --check
npx expo export --platform web
```

Testes locais usam SQLite **apenas como banco descartável de testes**, nunca como configuração do aplicativo. O workflow também executa a suíte contra MySQL 8.4. Para execução própria contra MySQL, configure `TEST_DATABASE_URL` com um banco descartável cujo nome termine em `_test`: a suíte apaga e recria suas tabelas.

O CI também verifica login e navegação web em larguras de 360, 768 e 1280 px com respostas de API simuladas, e salva capturas em seus artefatos. Esses testes de interface são separados dos testes da API real. Ainda é necessário validar entrega SMTP real, Groq com sua chave e comportamento em aparelho Android/iOS. A exportação web e checagem TypeScript não substituem testes de um APK/IPA.

## Estrutura

```text
app/                 API, modelos, validação, autenticação, relatórios
migrations/          Esquema versionado por Alembic
mobile/src/components/  Elementos visuais e formulários reutilizáveis
mobile/src/screens/     Telas por funcionalidade
mobile/src/stores/      Estado de autenticação e dados (Zustand)
mobile/src/lib/         Cliente HTTP, tipos e armazenamento seguro
tests/                 Regras de negócio e segurança da API
docs/                  Decisões, operação e migração
```

## Importar extratos

Em **Diário → Importar extrato**, selecione a instituição (10 opções), envie CSV,
OFX, XML, PDF textual ou DOCX e confira as entradas/saídas antes de confirmar.
PicPay possui adaptação para CSV e PDF por data agrupada, validada com amostra real.
Os outros perfis aceitam os contratos tabulares/OFX documentados; ainda exigem
amostras reais para validar variantes de layout. Horários e estabelecimentos
identificáveis seguem para o contexto criptografado. Layouts ambíguos são recusados. Consulte [formatos, segurança e configuração](docs/STATEMENT_IMPORTS.md).
Exige a migração `002_statement_imports`, chave privada `STATEMENT_ENCRYPTION_KEY`
e Linux/WSL para processamento limitado (Windows local somente com
`ENVIRONMENT=development` e `ALLOW_WINDOWS_IMPORT_DEV=true`). Produção exige também `DATABASE_SSL_CA`
para conexão MySQL com TLS validado; configure criptografia de volumes/backups.

## Pluggy (base mock)

Sincronização backend simulada, categorização e insights por regras: consulte
[configuração, endpoints e limites da integração](docs/PLUGGY.md).
Requer migração `003_pluggy_receipts`; habilitação explícita apenas fora de produção.


## Orientações e simulações (branch smart-insights-advisor)

A aba **Dicas** cruza padrões do diário com a meta selecionada, com simulações em centavos, custos de receitas por porção/embalagem e criptografia de metas, contextos e históricos. Escolha cidade do Paraná, meta e aporte planejado. Dados insuficientes não geram projeções inventadas.

**Ativação pendente:** não há fonte comercial de preços conectada; receitas mostram preços locais indisponíveis até configurar uma fonte autorizada. Push exige EAS/FCM/APNs, consentimento e execução do job. Não basta iniciar a API. Consulte [ADVISOR.md](docs/ADVISOR.md) para limites, contrato de preços, migração 004 e ativação. Pare a aplicação antiga e preserve a chave Fernet antes da migração.
