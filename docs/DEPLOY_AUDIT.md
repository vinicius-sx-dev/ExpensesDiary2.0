# Auditoria de preparação para deploy — 13/11/2026

## Conclusão e escopo

Revisão do código recebido em `ExpensesDiary - Copia.rar`, com correções e testes locais, preparado para publicação em um repositório novo, sem importar o histórico anterior. Os resultados locais abaixo não substituem o CI remoto; consulte a aba Actions para o resultado do commit publicado. O arquivo continha fontes, `.git`, ambientes instalados e arquivos `.env`; esses últimos não fazem parte da publicação. Não houve acesso ao banco real, uso de credenciais reais, teste de intrusão no servidor ou certificação de segurança.

A aplicação está preparada para continuar a homologação. **Não considerar aprovada para abertura pública irrestrita** antes dos requisitos operacionais abaixo. Severidades são estimativas qualitativas de impacto e exposição, não pontuações CVSS.

## Achados e ações

| Prioridade | Evidência e cenário | Correção / situação |
| --- | --- | --- |
| Alta se publicado | Arquivo de origem contém `.env` e histórico Git. Publicação indiscriminada poderia expor credenciais e dados anteriores. | Fontes extraídos por seleção, sem `.env`, histórico, dependências instaladas ou dados pessoais. `.gitignore` ampliado para cópias de env, chaves de assinatura, dumps e arquivos exportados. Varredura de padrões e comparação local com credenciais fornecidas não encontrou correspondências nos arquivos destinados ao commit. Isso não comprova ausência de exposições passadas. |
| Alta, condicionada à configuração | `environment` aceitava qualquer string. Um erro como `prod` pulava as validações de produção. Origens eram verificadas só por prefixo. | Enumeração estrita, hosts explícitos, validação estrutural das origens HTTPS, rejeição de segredos de exemplo/repetitivos e OpenAPI desativado em produção. Ainda é necessário gerar segredo aleatório; heurística não mede entropia. |
| Média | `BodyLimit` guardava uma lista por fragmento e não tinha prazo de leitura. Conexões lentas ou fragmentos vazios poderiam consumir recursos. | Buffer único limitado a 16 KiB e prazo total de 10 segundos; testes para fragmentação, excesso e timeout. Proteção de conexões/headers e DDoS continua sendo responsabilidade da borda. |
| Média | Refresh atrasado de uma sessão anterior podia chamar `clear()` na sessão nova; hidratação atrasada podia restaurar token após logout. | Refresh separado por geração, limpeza condicionada à mesma sessão e hidratação protegida. Dois testes executam as corridas com respostas atrasadas. |
| Média | Sem conexão, o botão sair preservava os dados da sessão no aparelho. | Opção explícita de sair localmente após falha remota, com aviso de que o token no servidor pode continuar válido. Teste em aparelho com SecureStore continua pendente. |
| Média | Limite da IA era apenas por usuário: várias contas multiplicavam custo. Consulta de relatórios podia repetir várias agregações por minuto. | Limite global de IA configurável (100/h por padrão), além de 5/h por usuário; leitura de relatórios limitada a 30/min por usuário. Teste verifica que o teto global bloqueia antes de chamar o provedor. Não equivale a teto monetário: configurar também orçamento e alertas no provedor. |
| Média | Contagem de objetivos podia usar snapshot antigo sob MySQL REPEATABLE READ após esperar lock da carteira. | Contagem por leitura com lock após serialização pelo usuário. É necessária validação de concorrência no MySQL de homologação. |
| Média, operacional | Suíte descartável herdava `DATABASE_URL`; SQLite era aceito sem distinguir banco real de banco de testes. | Testes usam SQLite temporário ou `TEST_DATABASE_URL` explícito com sufixo `_test` para MySQL. Nunca apontar esta variável para dados reais. |
| Baixa / usabilidade | Respostas 429/413 geradas fora do CORS podiam aparecer no navegador como erro de conexão. | CORS externo aos controles; testes verificam cabeçalhos de erro e Retry-After. |
| Alta para cadastro público | Cadastro reserva o e-mail antes de provar sua titularidade. Terceiro pode cadastrar e-mail alheio e impedir o dono de se cadastrar; não ganha acesso sem o OTP. Não há recuperação de senha. | Produção fecha novos cadastros por padrão. Abertura com `REGISTRATION_ENABLED=true` é opt-in explícito e mantém esse risco. Implementar cadastro pendente com expiração/confirmacão e recuperação com tokens de uso único antes de abrir aquisição pública. |

## Controles existentes verificados no código e nos testes

- **BOLA/IDOR e mass assignment:** proprietário derivado da sessão, filtros por usuário nas rotas privadas, campos extras recusados e testes de acesso cruzado. Não foi observado bypass no escopo inspecionado; não é prova universal.
- **SQL injection:** consultas SQLAlchemy parametrizadas; entradas com conteúdo de injeção não alteram o escopo de autorização nos testes.
- **Força bruta e credential stuffing:** limites por IP, instalação e conta; OTP de cinco tentativas, prazo e uso único. UUID de instalação é controlado pelo cliente e não substitui controle de IP/conta. Botnets e bloqueio direcionado por tentativas continuam riscos residuais.
- **Falsificação/replay:** algoritmo JWT fixo, issuer/audience/prazos, sessão consultada, refresh rotativo e revogação. Código por e-mail não é resistente a phishing; roubo conjunto de tokens e identificador permite uso da sessão até revogação/expiração.
- **Integridade financeira:** centavos inteiros, idempotência de lançamentos/aportes e serialização por usuário. Aporte reduz disponível e não duplica despesa de consumo. Testes cobrem insuficiência de saldo, aporte retroativo e exclusão que devolve disponível.
- **XSS e exportação:** interface usa componentes de texto; textos livres no HTML do PDF são escapados. PDF exportado contém dados financeiros em arquivo legível: usuário controla o destino e compartilhamento.
- **SSRF e prompt injection:** URL Groq fixa, TLS validado, sem ferramentas executáveis pela IA. Envio apenas de agregados, sem nomes, descrições ou títulos livres de metas. Comentários não alteram o banco; continuam sujeitos a erro e a tratamento de dados pelo provedor.
- **CSRF/CORS:** autenticação exige bearer e identificador, sem cookies de sessão. CORS não é autorização e não impede clientes fora do navegador.

## Validação executada

- Suíte Python local após as correções iniciais: 23 aprovados, 3 ignorados por exigirem MySQL; banco SQLite descartável.
- TypeScript: sem erros. Testes Node: 5 aprovados, incluindo duas regressões de sessão.
- Exportação web Expo: concluída. Checagem online do Expo falhou por timeout de proxy; checagem offline indicou dependências compatíveis, sem substituir a validação online.
- `npm audit`: zero vulnerabilidades conhecidas reportadas no lockfile consultado.
- `pip-audit -r requirements.lock --no-deps --disable-pip`: zero vulnerabilidades conhecidas reportadas. Lockfile instalado antes da auditoria; isso não cobre novas publicações futuras nem todo risco de cadeia de fornecimento.
- Testes de interface Playwright (360/768/1280 px): bloqueados localmente antes de abrir o navegador, por restrição de socket do Chromium (`Operation not permitted`); não são testes aprovados. O workflow repete a suíte em runner próprio.
- Não foram usados SMTP/Groq reais nem executados APK/IPA. Resultados adicionais da interface e CI devem ser consultados no repositório e no resumo da entrega.

## Pendências antes de uso real

1. HTTPS na borda, backend inacessível diretamente, proxies confiáveis explícitos, timeouts/limites de conexões e alertas de abuso. HSTS sozinho não configura TLS.
2. MySQL com InnoDB, credenciais mínimas, conexão privada/TLS quando remoto, backups criptografados com restauração testada. Executar testes de concorrência em MySQL descartável e migrações em homologação.
3. SMTP real (entrega, remetente, falhas e limites), chaves novas por ambiente e orçamento de IA. Revogar credenciais caso tenham sido publicadas anteriormente; a análise não constatou publicação anterior.
4. Fluxos de recuperação de conta, confirmação de cadastro, exclusão/exportação completa dos dados, política de privacidade e retenção definida. Sem esses fluxos, manter piloto controlado.
5. Testes de carga e de aparelhos: login, SecureStore, saída local, perda de rede durante refresh, PDF e acessibilidade com leitor de tela. Despesas essenciais não devem ser tratadas automaticamente como cortáveis.
6. Monitoramento e trilha de eventos sem tokens/dados financeiros. Não existe trilha contábil imutável; alterações legítimas mudam consultas ao vivo, não retratos históricos automaticamente.
7. Relatórios acumulados e validação de aportes ainda consultam histórico; volume alto exige medição e otimização. Janelas fixas permitem rajadas e limites por IP podem atingir usuários atrás do mesmo NAT.

## Referências técnicas

- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- Starlette, middleware e aplicação global de CORS: https://www.starlette.io/middleware/
