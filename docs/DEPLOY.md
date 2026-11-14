# Homologação e deploy

Leia primeiro [os achados e pendências](DEPLOY_AUDIT.md). Publicar o código no GitHub não publica a aplicação nem configura sua infraestrutura.

## Configuração

Use Python 3.12, MySQL 8.4/InnoDB e `pip install -r requirements.lock`. Injete segredos pelo ambiente/gerenciador de segredos. Não use credenciais do ambiente local e não exponha valores em comandos versionados.

- `ENVIRONMENT=production`: obrigatório no serviço real; outros valores aceitos são `development` e `test`.
- `DATABASE_URL`: usuário exclusivo do banco; dê permissões DDL apenas ao processo de migração, e DML à aplicação. Conexão remota precisa ser protegida na infraestrutura.
- `JWT_SECRET`: gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"` e armazene como segredo. Não reutilize exemplos.
- `ALLOWED_HOSTS`: JSON com hostname da API, sem protocolo, porta, wildcard ou localhost. Exemplo não secreto: `["api.seudominio.com"]`.
- `CORS_ORIGINS`: JSON com origens HTTPS exatas, sem caminho. `[]` é válido se somente clientes nativos acessarem a API.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`: obrigatórios para produção, STARTTLS validado.
- `GROQ_API_KEY`: opcional e somente no backend; `GROQ_MODEL` deve corresponder a modelo habilitado no provedor.
- `AI_GLOBAL_HOURLY_LIMIT`: teto global de chamadas por hora, padrão 100, além do limite individual. A janela é fixa; configurar limites de orçamento também no provedor.
- `REGISTRATION_ENABLED`: produção assume `false`. `true` habilita o cadastro atual, que ainda não confirma e-mail antes de reservá-lo. Manter piloto controlado até implementar o fluxo pendente de confirmação/recuperação.

Se utilizar o arquivo `.env.example`, substitua `ENVIRONMENT=development` por `production` e altere hosts/origens. Não leve a configuração local intacta ao servidor.

## Sequência operacional

1. Fazer backup e testar restauração. Em banco legado, seguir `MIGRATION.md`; nunca assumir que um esquema anterior é compatível só porque existe `users`.
2. Executar `alembic upgrade head` com credencial de migração em homologação antes da produção.
3. Colocar proxy HTTPS na frente do Uvicorn e bloquear acesso externo direto à porta da aplicação. Exemplo para proxy na própria máquina:

   ```sh
   uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1 --limit-concurrency=100 --timeout-keep-alive=5
   ```

   Ajustar os limites após medir carga. Em contêineres, usar somente IPs/redes efetivamente confiáveis e regras de rede; nunca liberar proxy headers de qualquer origem. O proxy deve repassar Host autorizado e IP real, limitar cabeçalhos/corpo/conexões e tempos de leitura. O serviço deve reiniciar sob supervisão e executar sem root.
4. Confirmar `/health`, rejeição de Host inválido, ausência de `/docs` e `/openapi.json`, e login/OTP real. Não registrar query strings, Authorization, corpos ou respostas financeiras nos logs do proxy.
5. Agendar `python -m app.maintenance` diariamente e `python -m app.weekly_job` às segundas no fuso America/Sao_Paulo. Alertar em caso de falha; não há cron embutido.
6. Gerar app com `EXPO_PUBLIC_API_URL=https://...`, instalar em aparelho e testar; essas variáveis são públicas e não podem conter segredos. Exportação web exige hospedagem HTTPS e política de segurança do frontend revisada.
7. Habilitar alertas de erros 5xx/429, latência, pool SQL, tentativas de login, despesas do provedor e falhas de backup, sem dados privados.

## Testes de banco

`python -m pytest -q` usa SQLite temporário por padrão e ignora `DATABASE_URL` para selecionar o banco de testes. Para MySQL defina **TEST_DATABASE_URL** apontando para banco novo descartável com nome terminado em `_test`. A suíte apaga/recria tabelas. Nunca usar banco real, mesmo com esse sufixo. O workflow do repositório cria seu próprio MySQL descartável.

## Limitações para o usuário

Perder a resposta de rotação do refresh pode exigir novo login. Sair somente do aparelho não revoga o token remoto. Sem recuperação de senha, conta esquecida exige um procedimento seguro ainda não implementado. Comentários de IA não são armazenados no retrato; exporte o relatório exibido para guardá-los. O diário não concilia saldo bancário e permite registrar despesas reais mesmo com saldo negativo.
