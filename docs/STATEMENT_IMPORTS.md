# Importação de extratos

Na tela **Diário → Importar extrato**, selecione um arquivo, confira os valores e
marque as linhas que deseja importar. A confirmação grava entradas/saídas no mesmo
livro de lançamentos utilizado pelo saldo, metas e relatórios. Categoria inicial:
`outros` / `outras_receitas`; meio de pagamento: `other`; descrição vazia.

O seletor de instituição é obrigatório. São extraídos data, valor em centavos e direção;
quando explicitamente identificáveis, horário e estabelecimento alimentam o schema
unificado (`make_entry` / `MovementContext`). CPF, conta, agência e nomes de pessoas
em transferências Pix não são persistidos. Descrições livres não viram estabelecimentos:
usamos colunas explícitas ou prefixos de compra reconhecidos. Documentos em campos de
estabelecimento são removidos; links, markup e controles perigosos são recusados.
Não há serviço externo/IA lendo o arquivo. O arquivo original permanece em memória,
inclusive durante o multipart, e não é gravado no repositório ou banco. No app nativo,
a cópia do seletor no cache é removida; o original do usuário não é apagado.

## Diagnóstico da falha corrigida

- O transporte anterior era binário (`application/octet-stream`), compatível entre app
  e servidor; não era multipart. Agora ambos usam `file` + `institution` em FormData.
  O cliente deixa o fetch gerar `Content-Type` e boundary, mantendo Bearer e X-Device-ID.
- No PDF PicPay, a data vem no cabeçalho do grupo por extenso e as linhas têm horário.
  O leitor anterior exigia data completa por linha e não reconhecia esse layout.
- No CSV PicPay, `tipo` contém a operação, não C/D; há `origem / destino`, `forma de
  pagamento` e o sinal Unicode `−`. O parser anterior rejeitava colunas e sinal.
- PDFs reais usam mapas de fontes ToUnicode. O codec UTF-16 era carregado tardiamente
  depois do bloqueio de filesystem do worker: o teste direto passava e o worker
  levantava PermissionError. Agora codecs são pré-carregados antes do audit hook,
  mantendo o bloqueio. Um PDF sintético com ToUnicode cobre essa regressão via HTTP.

## Formatos e compatibilidade real

`app/statement_parsers` contém o registro/factory de estratégias imutáveis. A estratégia
PicPay trata CSV e PDF próprios; as demais configuram aliases e identidade da instituição
sobre os leitores seguros compartilhados. Não se alteram aliases globais por requisição.

| Identificador | Instituição | Cobertura e evidência |
| --- | --- | --- |
| PICPAY | PicPay | CSV fornecido e PDF real de 17 páginas validado via HTTP/worker: 118 linhas. PDF agrupado por data, nomes quebrados, rodapés e horários. |
| NUBANK | Nubank | Contrato Data/Valor/Identificador/Descrição; fixture sintética. |
| BANCO_DO_BRASIL | Banco do Brasil | Aliases Data movimento/Lote/Histórico/Documento/Valor R$; fixture sintética. |
| ITAU | Itaú | Data/Lançamento/Ag./Origem/Valor (R$)/Saldo (R$); fixture sintética. |
| BRADESCO | Bradesco | Data/Histórico/Docto./Crédito (R$)/Débito (R$)/Saldo (R$); fixture sintética. |
| SANTANDER | Santander | Data de movimentação/Descrição do lançamento/Valor (R$); fixture sintética. |
| CAIXA | Caixa Econômica Federal | Data mov./Nr. doc./Histórico/Valor (R$), sufixos C/D; fixture sintética. |
| BTG | BTG Pactual | Data de liquidação/Descrição do movimento/Valor (R$); fixture sintética. |
| SICREDI | Sicredi | Data lanc./Num. documento/Histórico/Valor (R$); fixture sintética. |
| MERCADO_PAGO | Mercado Pago | DATE/TRANSACTION_TYPE/REFERENCE_ID/TRANSACTION_NET_AMOUNT; fixture sintética. |

**Os nove perfis sem amostra real não são homologação dos extratos de produção desses
bancos.** Variantes não reconhecidas continuam recusadas. Fixtures sintéticas validam
os contratos implementados e a integração HTTP, não a totalidade dos layouts comerciais.

| Formato | Contrato aceito |
| --- | --- |
| CSV | UTF-8/BOM ou Windows-1252; vírgula, ponto e vírgula ou tab. Cabeçalho reconhecido após até 29 linhas de preâmbulo. Data + valor assinado ou crédito/débito. PicPay usa seis colunas específicas, horário e operação. Colunas desconhecidas e linhas inconsistentes são recusadas. |
| OFX | OFX 1.x SGML e 2.x XML em BRL, STMTTRN/DTPOSTED/TRNAMT. BANKID verifica instituição quando reconhecido. Conta, FITID e MEMO não são persistidos. |
| XML | OFX, camt.053.001.xx contabilizado BOOK em BRL com BookgDt/Dt, ou esquema simples abaixo. |
| PDF | PicPay por data agrupada; nos demais perfis, tabela explícita com datas completas e colunas reconhecidas. Máximo 100 páginas. Sem OCR, conteúdo ativo, links, formulários, anexos ou senha. |
| DOCX | Uma tabela reconhecida; valida emissor em parágrafos externos à tabela. Sem DOC, DOCM, macros, imagens, objetos, campos e relações externas. |

A validação cruzada usa metadados de emissor, assinatura do cabeçalho PicPay e BANKID
OFX. Não procura bancos dentro de descrições de transferências. A ausência de identidade
não prova qual banco emitiu o arquivo: um layout neutro compatível pode ser importado.

XLS/XLSX, imagens, ZIP avulso e outros formatos não são aceitos nesta versão.
Para documentos recusados, prefira exportar CSV ou OFX diretamente da instituição.
Não há OCR, LLM, execução de Office/LibreOffice nem conversão de documentos ativos.

Exemplo CSV:

```csv
Data;Valor;Tipo
01/11/2025;1000,00;C
02/11/2025;45,90;D
```

Valor sem Tipo usa o sinal: positivo = entrada, negativo = saída. Não importar
fatura de cartão como extrato de conta: o sinal e a contabilização são diferentes.
`1.234` é ambíguo e recusado; use `1234,00`, `1.234,00` ou `1234.00`.
Resumos explicitamente identificados como saldo anterior/final ou total de entradas/saídas
são ignorados; linhas datadas ambíguas com saldo/total são recusadas.
Datas aceitas: dd/mm/aaaa, aaaa-mm-dd, dd-mm-aaaa, dd.mm.aaaa, desde 2000 até hoje.

XML simples (também aceita `statement/transaction` e `date/amount/direction`):

```xml
<extrato moeda="BRL">
  <movimentacao><data>01/11/2025</data><valor>100,00</valor><tipo>C</tipo></movimentacao>
</extrato>
```

## Duplicidades e efeitos financeiros

O mesmo arquivo confirmado é bloqueado por HMAC por usuário. A confirmação é
idempotente e usa o mesmo lock do caixa; duas confirmações não criam duas cópias.
Prévia/consulta/descarte/confirmação verificam o proprietário.
Para arquivos diferentes ou sobrepostos, compara data + direção + valor com os
lançamentos existentes, preservando a multiplicidade. Possíveis duplicatas começam
desmarcadas; o usuário pode selecionar explicitamente uma movimentação legítima.
Sem conta/FITID/descrição não é possível provar identidade entre transações iguais.
Não há deduplicação perfeita entre bancos/formatações. Transferências entre contas
próprias precisam ser conferidas; não são identificadas automaticamente.

Somente as linhas selecionadas são gravadas, em uma transação. Após confirmar,
o arquivo fica marcado como confirmado mesmo que a seleção seja parcial; corrija
lançamentos individualmente ou importe um novo arquivo contendo apenas o restante.
Saldo inicial não é importado. Histórico incompleto pode produzir saldo negativo;
o saldo exibido é o fluxo registrado e não uma conciliação bancária garantida.

## Limites e contenção

- Autenticação e limites antes da leitura do corpo; multipart com um arquivo e instituição.
- Envelope multipart limitado a 5 MiB + 64 KiB; arquivo limitado a 5 MiB.
  Até dois campos de texto durante parsing (256 bytes cada), contrato final exatamente
  um `institution` e um `file`; duplicatas e campos extras são recusados.
  Spool em memória, fechado em sucesso ou erro, sem temporários no disco.
- 5 MiB por arquivo, 2.000 movimentos, 100 páginas PDF e 2 MiB de texto extraído.
- DOCX: até 150 membros, 10 MiB descompactados totais, 2 MiB por membro,
  razão de compressão máxima 100:1; sem extração para disco.
- 6 envios/minuto e 120/dia por usuário (também contam tentativas inválidas).
  Permite importar dez anos de arquivos mensais em um dia, respeitando as pausas.
- Limite global configurável `IMPORT_GLOBAL_HOURLY_LIMIT` (padrão 300).
- Duas vagas globais de upload/processamento em SQL entre workers, com leases de
  60 segundos; resposta 429 + Retry-After se ocupado, sem fila ilimitada.
- Prazo de upload 20 s; subprocesso 12 s de relógio, 8 s CPU, 384 MiB RAM;
  falha/timeout encerra o subprocesso sem gravação parcial.
- Até três prévias pendentes por usuário, válidas por uma hora. Rotina de manutenção
  remove prévias expiradas; confirmação elimina imediatamente o payload da prévia.

Leitura de documentos necessariamente envolve parsing. MIME/extensão não provam
segurança: o servidor valida também assinatura, estrutura e semântica. XML usa
`defusedxml` sem DTD/entidades externas. PDF percorre os objetos referenciados para
recusar ações ativas; DOCX recusa componentes externos/ativos. Conteúdo estranho ou
ambíguo gera erro genérico sem eco do arquivo ou traceback do parser.

O subprocesso inicia sem variáveis de credenciais da aplicação, carrega bibliotecas
antes de bloquear acesso a arquivos/rede/processos via audit hook e impõe limites
POSIX. **Isso é contenção em camadas, não uma sandbox de sistema operacional nem
certificação antivírus.** Em produção, executar a API sob usuário sem privilégios,
filesystem somente leitura, sem montagem de segredos desnecessários, e limites de
CPU/memória do contêiner. Não prometer ausência de malware por validação de formato.
Produção requer Linux/WSL. Windows local é permitido apenas com
`ENVIRONMENT=development` e `ALLOW_WINDOWS_IMPORT_DEV=true`, preservando os limites
de bytes, timeout e audit hook, mas sem os limites POSIX de CPU/memória.

## Criptografia e implantação

1. Instale `requirements.lock` e execute `alembic upgrade head`.
2. Gere uma chave **independente do JWT**, em ambiente seguro:

   ```sh
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Configure `STATEMENT_ENCRYPTION_KEY` no gerenciador de segredos/.env privado.
   Sem a chave, somente importação fica indisponível (503). Nunca colocar no app,
   código, imagem do contêiner, logs ou Git. Fernet fornece criptografia autenticada
   da prévia; o conteúdo inclui usuário e ID para impedir troca entre registros.
   Trocar a chave invalida prévias pendentes e altera os HMACs de deduplicação de
   arquivo: planeje a rotação, confirme/descarte prévias e mantenha a revisão de
   duplicatas. Não rotacionar rotineiramente sem migração dos HMACs.
3. Produção exige `DATABASE_SSL_CA=/caminho/ca-mysql.pem`. O driver usa SSLContext
   com validação da cadeia e hostname, TLS mínimo 1.2. Nome do host da DATABASE_URL
   deve corresponder ao certificado; falha não permite fallback sem TLS.
   Ative `require_secure_transport=ON` no MySQL e `REQUIRE SSL` no usuário.
   Se houver TLS por mTLS, adaptar a configuração de certificado cliente.
4. HTTPS entre app e API é obrigatório na versão de produção do app. Termine TLS
   no proxy, não exponha diretamente a porta interna da API, limite o corpo a
   5 MiB + 64 KiB para acomodar o envelope multipart, imponha timeouts e limite de conexões. Desative buffering de uploads para
   disco, gravação de corpo de requests, traces de payload e swap/core dumps sem
   criptografia. Não registrar cabeçalhos de autenticação nem dados financeiros.
5. Configure criptografia de volumes/tablespaces e backups no provedor/MySQL e
   guarde chaves fora do banco. **Lançamentos confirmados mantêm campos numéricos
   consultáveis do modelo existente: não são criptografados campo a campo.**
   Estabelecimento/horário ficam em `protected_context`, criptografado com Fernet
   e vinculado a usuário/request_id. O escopo de criptografia não foi ampliado.
   TLS protege envio ao banco; a prévia tem criptografia na aplicação; a proteção
   dos dados definitivos em repouso depende da infraestrutura. Não são equivalentes.
6. Agende `python -m app.maintenance` ao menos a cada hora para limpar prévias
   expiradas. Restrinja acesso ao banco e monitore apenas métricas agregadas.
7. Mobile: `npm ci`, Expo Go compatível ou reconstrução do aplicativo nativo para
   incluir `expo-document-picker`. Teste Android/iOS reais antes do release.

Os controles de upload seguem as recomendações de
[OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
e os limites de extração descritos no [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

## API

`POST /imports/preview` recebe `multipart/form-data` com `file` (nome/extensão e MIME)
e `institution` (um dos identificadores acima), Bearer e X-Device-ID. O cliente não
define Content-Type manualmente. Retorna id, expires_at, rows (index/data/valor/direção,
context quando disponível, possible_duplicate) e totais.

Compatibilidade com clientes binários: `POST /imports/preview?format=csv&institution=PICPAY`
ainda aceita bytes; instituição é obrigatória também nesse contrato. Atualize clientes
antigos que não enviam instituição. Não há migração de banco nova nesta mudança.

`GET /imports` lista prévias; `GET /imports/{id}` retoma;
`DELETE /imports/{id}` descarta; `POST /imports/{id}/confirm` recebe
`{"selected":[0,1]}`. O cliente nunca reenvia valores editados para confirmar.

Erros: 400 envelope inválido; 413 tamanho; 415 formato/MIME; 422 seleção/layout/banco
incompatível; 429 limites; 503 worker indisponível; 504 tempo de processamento excedido. `X-Error-Code` diferencia
`institution_mismatch`, `unsupported_layout`, `invalid_institution` e
`worker_unavailable` / `processing_timeout` sem expor texto, nomes de arquivos ou stack traces.

## Validação

```sh
python -m pytest -q
cd mobile
npm run typecheck
node --experimental-strip-types --test tests/*.test.mjs
```

`tests/test_bank_statement_uploads.py` envia multipart real para as dez estratégias,
passa pelo subprocesso real, verifica prévia criptografada e confirma os lançamentos.
Cobre CSV, PDF, OFX e DOCX, emissor incompatível, tamanho/MIME, autenticação, rate limit,
CORS, codecs Unicode e saneamento. Os testes anteriores continuam cobrindo XML,
XXE, conteúdo ativo, bomba ZIP, isolamento de usuário, expiração, saldo e idempotência.
O teste concorrente exige MySQL e roda no CI. As fixtures versionadas são fictícias.

Para repetir a validação da amostra privada, opcionalmente defina
`PRIVATE_STATEMENT_PDF=/caminho/privado.pdf` e execute somente
`tests/test_bank_statement_uploads.py::test_private_picpay_pdf_full_http`.
Esse teste é específico da amostra de 118 movimentos e não grava seu conteúdo no Git.

A suíte Playwright verifica as dez opções, seleção obrigatória, corpo multipart com
boundary gerado pelo browser, autenticação, revisão e confirmação em três larguras.
A suíte de transporte também verifica o reenvio de FormData após renovar token.
Testes de interface usam respostas simuladas; testes HTTP usam o backend real.
Teste Android/iOS físicos antes do release; o ambiente de desenvolvimento aqui é Linux.
