# Pluggy: base mock

Esta fase é uma API backend de simulação, sem comunicação com bancos. Não usa ML.
Ative `PLUGGY_MOCK_ENABLED=true` apenas em desenvolvimento/teste, configure
`STATEMENT_ENCRYPTION_KEY` e execute `alembic upgrade head`.
As credenciais PLUGGY_CLIENT_ID/PLUGGY_CLIENT_SECRET estão reservadas: preenchê-las
não ativa um cliente real. O contrato Provider permite adicionar esse adaptador.

Com os mesmos Authorization Bearer e X-Device-ID do aplicativo:

- GET /pluggy/mock/accounts retorna a conta simulada sem número/agência/documentos.
- POST /pluggy/mock/sync com `{}` registra salário, mercado e restaurante simulados.
- Com `{"investment_goal_id": 123}`, também registra o investimento na meta pertencente
  ao usuário. Sem associação, contabiliza `awaiting_goal` e permite processar depois.
- GET /pluggy/insights retorna alertas determinísticos dos orçamentos e metas atuais.

Há um conjunto fixo de movimentos por mês; repetir sincronização não duplica valores.
Recibos opacos persistem mesmo se o usuário apagar o lançamento. Aportes não são
contados novamente como despesas. Contas são descobertas pelo provedor mock, sem
registro persistente de conexões. Não há interface mobile nesta fase.

Os dados normalizados usam campos do contrato oficial:
https://docs.pluggy.ai/en/docs/products/transactions
O schema é um subconjunto estrito, não um validador de todas as respostas Pluggy.
O futuro adaptador deve descartar campos não necessários antes da validação e lidar
com paginação, correções, exclusões, moedas, cartões, transferências internas e
resgates. A classificação atual usa categorias explícitas e fallback Outros;
valores entram no cálculo dos limites, não são usados para adivinhar o nicho.

## Segurança e armazenamento

Prévia manual continua Fernet. A sincronização automática não persiste payload bruto,
CPF, número de conta, descrição ou credenciais. Guarda apenas lançamentos normalizados
em texto plano conforme decisão de arquitetura. Exige chave configurada para manter
compatibilidade com o fluxo de importação. Não cria prévia persistente da Pluggy.
Dados ficam em memória durante processamento; a resposta de sync contém só contagens.
O acesso é autenticado e filtrado por usuário; meta alheia recebe 404. Há lock por
carteira, unicidade dos recibos, limites por usuário/globais e limites de corpo/IP
existentes. Simulação é bloqueada em produção. CORS não substitui autenticação.

Nenhum webhook público foi habilitado. Antes de ativar um adaptador real, registrar
as conexões por usuário e implementar autenticação de webhook com header secreto
configurado no cadastro Pluggy, comparação constante e proteção contra repetição.
Não confiar em URLs vindas dos eventos; buscar dados pelo endpoint fixo do provedor.

Banco de produção: TLS validado já é exigido; conexões agora têm timeout e pool
limitado. Configurar rede privada/firewall sem porta MySQL pública, usuário exclusivo
com SELECT/INSERT/UPDATE/DELETE, credencial de migração separada, discos/backups
criptografados e testes de restauração. Não habilitar general_log ou SQL echo com
dados de usuários. Credenciais devem ficar no gerenciador de segredos do deploy.
Essas medidas de infraestrutura precisam ser aplicadas no ambiente de hospedagem;
o código não configura nem verifica o firewall ou a criptografia dos discos.

Não é proteção absoluta contra DDoS: limitar conexões e tráfego no proxy/WAF antes da
API. Os limites da aplicação dependem do banco e são uma camada adicional.
