# Segurança e operação

## Problemas corrigidos da versão inicial

Rotas de consulta/alteração/exclusão arbitrária de usuários eram públicas. O chat compartilhava uma lista de mensagens global entre contas. O cliente HTTP da IA desativava a verificação TLS. Exceções internas eram devolvidas ao cliente, dados financeiros eram impressos em logs, o JSON de gastos não validava domínio e o relatório devolvia objeto em um schema que esperava string.

As rotas antigas foram removidas. O perfil é acessível apenas por `/auth/me`. Todos os recursos privados derivam o proprietário da sessão e filtram por `user_id`; IDs inexistentes e pertencentes a outra conta retornam o mesmo 404. Não existe papel administrativo exposto neste MVP.

## Autenticação

- Argon2 via pwdlib; mínimo de 12 e máximo de 128 caracteres para novas senhas. Hash fictício na verificação de conta inexistente. Senhas não sofrem trim silencioso.
- Cadastro responde genericamente para reduzir enumeração. Login inválido também é genérico.
- Senha + código de e-mail obrigatório em cada novo login. Seis dígitos gerados com CSPRNG, cinco minutos, cinco tentativas, uso único, hash HMAC com segredo fora do banco. Novo desafio invalida o anterior; verificação serializada por lock SQL.
- E-mail é uma segunda etapa de menor garantia que TOTP/WebAuthn e não é resistente a phishing. Comprometimento do e-mail reduz a proteção. Não há recuperação de senha automática nem alteração de e-mail neste MVP: não improvisar uma rota que contorne a segunda etapa.
- JWT HS256 com algoritmo fixo, issuer/audience, sub, sid, iat, nbf, exp, jti e type. Access token dura 10 minutos, vinculado a uma sessão ativa consultada no banco.
- Refresh opaco de alta entropia, somente hash no banco, rotativo e com prazo absoluto de 30 dias. Reuso revoga a sessão. Logout revoga imediatamente; logout-all disponível na API. Se a resposta de rotação se perder na rede, um novo login pode ser necessário.
- Instalação identificada por UUID no SecureStore e vinculada à sessão. É uma identificação lógica, não atestado de hardware: o cliente pode inventar IDs. IP e conta sempre limitam junto.

## Limites

| Escopo | Janela / limite |
| --- | --- |
| IP global | 300/minuto |
| IP autenticação | 30/15 minutos |
| instalação autenticação | 20/15 minutos |
| conta no cadastro/login | 10/15 minutos |
| usuário autenticado | 180/minuto |
| instalação autenticada | 180/minuto |
| salvar relatório | 10/hora |
| comentários IA por usuário | 5/hora |
| comentários IA global | 100/hora por padrão |
| consulta relatório semanal | 30/minuto por usuário |

Contadores SQL com incremento condicional atômico, compartilhados entre workers; 429 com Retry-After. Janelas fixas permitem rajadas na virada da janela. A limpeza diária remove registros expirados. Falha no banco não desativa silenciosamente o limitador. Em tráfego elevado, avaliar um limitador de borda/Redis; não necessário para esta base.

## Infraestrutura

Execute atrás de HTTPS com proxy configurado, limite de conexões, timeout de cabeçalhos/corpo e proteção a conexões lentas. O app limita o corpo real recebido a 16 KiB; isso não substitui timeouts de rede. Não confie em `X-Forwarded-For` de qualquer origem. Localmente use `--no-proxy-headers`; em produção habilite encaminhamento somente dos IPs conhecidos do proxy (`--forwarded-allow-ips`). Bloqueie acesso direto ao servidor de aplicação. Confirme que o IP chega corretamente para não limitar todos os usuários como se fossem um único proxy.

CORS com lista explícita, TrustedHost, no-store, nosniff, frame denial e HSTS em produção. Nenhuma autenticação em cookie; não confiar em CORS para autorização. Erros de validação omitem valores de entrada; erros internos não expõem SQL, stack traces, tokens ou credenciais. TLS da Groq e SMTP sempre verificado. Não registrar corpos, cabeçalhos Authorization, códigos, senhas ou dados financeiros em access logs.

Use MySQL InnoDB e usuário SQL restrito. SQLAlchemy parametriza consultas; não há concatenação de SQL com entrada do cliente. Validação explícita e `extra=forbid` impedem mass assignment; o cliente não escolhe o proprietário. Para migrações, use credencial DDL separada da credencial de execução se possível. Proteja backups e aplique retenção apropriada.

Segredos ficam em `.env` ignorado ou no secret manager do servidor. Rotacionar `JWT_SECRET` invalida tokens, desafios, hashes de refresh e identificadores de instalação armazenados no servidor: planeje novo login para todos. Não usar o valor do arquivo de exemplo.

## Limites desta entrega

Não é uma auditoria externa nem promessa de segurança absoluta. Falta validação com SMTP/Groq reais e em aparelhos; o CI inclui MySQL para validar diferenças que SQLite não cobre. Dados anteriores em JSON não são reinterpretados sem uma regra explícita. A exclusão/edição de lançamentos altera consultas ao vivo, enquanto retratos salvos só mudam se forem gravados novamente. Não há trilha imutável de auditoria forense: o diário atende à revisão pessoal dos gastos.

## Dependências

O SDK Expo 58 é acompanhado por lockfile. Há um override restrito de `minimatch` em `@expo/fingerprint` para a versão corrigida 11.0.1+, devido ao GHSA-g3hv-75wg-m249. A geração de fingerprint é verificada após esse ajuste; reavalie o override quando o Expo atualizar a dependência. Não executar `npm audit fix --force` indiscriminadamente, pois pode sugerir um downgrade incompatível do SDK.

## Revisão de deploy

Consulte [DEPLOY_AUDIT.md](DEPLOY_AUDIT.md) para achados, correções e riscos residuais desta publicação, e [DEPLOY.md](DEPLOY.md) para a configuração. Cadastro de produção fechado por padrão até concluir confirmação de e-mail/recuperação.
