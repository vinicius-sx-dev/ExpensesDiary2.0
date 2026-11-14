# Importação de extratos

Na tela **Diário → Importar extrato**, selecione um arquivo, confira os valores e
marque as linhas que deseja importar. A confirmação grava entradas/saídas no mesmo
livro de lançamentos utilizado pelo saldo, metas e relatórios. Categoria inicial:
`outros` / `outras_receitas`; meio de pagamento: `other`; descrição vazia.

Somente **data, valor em centavos e direção** são extraídos para a prévia. CPF,
conta, agência, nomes de terceiros, locais, descrições e nome do arquivo não são
persistidos nem enviados a IA/antivírus/serviços externos. O arquivo original fica
somente na memória durante a requisição e é descartado. No app nativo, a cópia
criada pelo seletor no cache é removida após o envio; o original do usuário não é apagado.

## Formatos e compatibilidade real

O importador identifica **estruturas**, não a marca do banco. Não existe homologação
universal de BB, PicPay, Bradesco, Itaú, Nubank ou qualquer outra instituição.
Exportações dessas instituições podem funcionar se corresponderem aos contratos
abaixo. Os testes são sintéticos e não demonstram cobertura de todos os bancos.
Para acrescentar adaptadores, usar amostras anonimizadas e testes de totais/direção.

| Formato | Contrato aceito |
| --- | --- |
| CSV | UTF-8/BOM ou Windows-1252, delimitadores vírgula/ponto e vírgula/tab. Cabeçalho na primeira linha: data + valor assinado, ou data + crédito + débito. Tipo C/D opcional. Aliases em `statement_parser.ALIASES`. Colunas desconhecidas e linhas inconsistentes são recusadas. |
| OFX | OFX 1.x SGML e 2.x XML, `CURDEF=BRL`, `STMTTRN`, `DTPOSTED`, `TRNAMT` assinado. Não utiliza conta/FITID/memo. |
| XML | OFX; ISO 20022 camt.053.001.xx, apenas Ntry contabilizado BOOK, BRL, BookgDt/Dt; ou esquema simples descrito abaixo. Não aceita XML fiscal ou documento arbitrário. |
| PDF | PDF com texto, até 100 páginas, tabela com cabeçalho reconhecido, colunas separadas por espaços e datas completas. Conteúdo ativo, links, formulários, anexos, senha, imagem/OCR e layout ambíguo são recusados. Não tenta adivinhar o sinal pela descrição. |
| Word | DOCX com uma tabela reconhecida. Não aceita DOC binário, DOCM, macros, imagens, objetos incorporados, campos ou relações externas. |

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
Linhas de saldo/total dentro de uma tabela CSV são recusadas, não contabilizadas.
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

- Autenticação e limites antes da leitura do corpo; corpo binário, sem multipart/base64.
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
O importador requer Linux/WSL; no Windows puro retorna 503 para não perder limites.

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
   5 MiB, imponha timeouts e limite de conexões. Desative buffering de uploads para
   disco, gravação de corpo de requests, traces de payload e swap/core dumps sem
   criptografia. Não registrar cabeçalhos de autenticação nem dados financeiros.
5. Configure criptografia de volumes/tablespaces e backups no provedor/MySQL e
   guarde chaves fora do banco. **Lançamentos confirmados mantêm campos numéricos
   consultáveis do modelo existente: não são criptografados campo a campo.**
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

`POST /imports/preview?format=csv` recebe corpo binário com Bearer e X-Device-ID;
retorna id, expires_at, rows (index/data/valor/direção/possible_duplicate) e totais.
`GET /imports` lista prévias pendentes; `GET /imports/{id}` retoma uma prévia;
`DELETE /imports/{id}` descarta; `POST /imports/{id}/confirm` recebe
`{"selected":[0,1]}`. O cliente nunca reenvia valores editados para confirmar.

## Validação

Testes cobrem CSV/XML/OFX/DOCX/PDF sintéticos, arquivos falsos, XXE, conteúdo ativo,
bomba ZIP, limites de envio, isolamento de usuário, expiração, criptografia,
deduplicação, saldo e idempotência. Teste concorrente exige MySQL e roda no CI.
A suíte de interface verifica seleção, revisão e confirmação em larguras diferentes.
