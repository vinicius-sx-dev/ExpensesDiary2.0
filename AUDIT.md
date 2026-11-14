> Registro histórico da branch anterior. Para a auditoria desta publicação, consulte [docs/DEPLOY_AUDIT.md](docs/DEPLOY_AUDIT.md). As referências a PR #1 e branch abaixo pertencem ao repositório antigo.

# Auditoria de integração — 13/11/2026

Escopo: rotas, autenticação, middleware, persistência, validação, estado mobile,
formulários, relatórios e exportação no branch feat/secure-finance-mobile.

## Falhas reproduzidas e corrigidas

- Home apresentava fluxo semanal antes dos aportes como número principal. Agora
  mostra saldo acumulado até a data do relatório: receitas − despesas − aportes.
- API aceitava aportes sem origem de recursos. Validação no servidor e lock por
  usuário serializam mutações do caixa, inclusive aportes em objetivos diferentes.
  Aporte retroativo não pode usar renda futura nem comprometer fluxos posteriores.
- Diário omitia aportes. `/movements` reúne lançamentos e aportes com paginação;
  não duplica registros. A exclusão usa o endpoint correto e libera o disponível.
- Falha em um endpoint apagava o carregamento de toda a Home. Cargas independentes
  agora preservam resultados válidos; saldo indisponível não aparece como zero.
- Resposta textual (como Invalid host header) era confundida com erro de conexão.
  Cliente HTTP agora distingue status HTTP e JSON inválido e valida o protocolo.
- Resposta JSON válida da IA podia falhar apenas por ultrapassar 1200 caracteres.
  Limites locais agora aceitam respostas maiores, ainda limitadas. Truncamento,
  recusa, formato inválido, rede, chave, configuração e limite do provedor possuem
  diagnósticos distintos sem expor resposta bruta, chave ou dados financeiros.
- `.env` dependia do diretório de execução. Caminho agora é relativo à raiz da API.
- PDF no Android só abria compartilhamento. Agora oferece escolha de pasta via
  Storage Access Framework; cancelar abre compartilhamento como alternativa.
  Há botão independente para reexportar o relatório exibido, incluindo a análise
  de IA exibida, e falha de exportação após salvar não é confundida com falha de gravação.
- Relatório recém-salvo não entrava no histórico local. Agora é inserido/substituído.
- Resposta tardia de paginação podia alterar estado de uma sessão encerrada.
  Erro e loading também respeitam a geração da sessão. Repetição de pedido após
  refresh não pode reutilizar uma operação da sessão anterior em outra conta.

## Regras contábeis

Aporte é saída do disponível para uma reserva de objetivo, não consumo.
`expense_cents` e orçamentos de consumo excluem aportes; `reserved_cents` é
semanal, `reserved_total_cents` acumulado e `available_cents` acumulado líquido.
Não lance manualmente o aporte como despesa. Registre a origem em Receitas.
Correções de lançamentos reais podem deixar o saldo negativo: o app deve mostrar
isso, não impedir o registro de uma despesa real. Novos aportes sem cobertura são
bloqueados. Registros antigos são contabilizados sem criar débitos duplicados.
Snapshots antigos continuam históricos e não são reescritos automaticamente.

## Limites da verificação

Testes da IA usam HTTP simulado: não comprovam validade da chave, cota ou rede
na máquina do usuário. O antigo 503 isolado não identifica qual dessas causas
ocorreu. Consulte o novo código AI_* retornado pela API/log, sem divulgar a chave.
Não foi executado APK em aparelho físico; o caminho Android requer as dependências
nativas atuais e, para development builds, recompilação após adicioná-las.
Comentários da IA não são persistidos no snapshot; exporte o relatório exibido
após pedir a análise para incluí-los. Salvar/reabrir um snapshot exporta os números.
Isso é uma limitação funcional conhecida, não uma análise salva silenciosamente.
O MVP não confere saldo bancário nem possui conciliação ou contas separadas.
Não é uma certificação de ausência de vulnerabilidades.

## Atualização local

As mudanças estão no branch `feat/secure-finance-mobile` (PR #1); main ainda é a
versão inicial. Atualize esse branch sem sobrescrever alterações locais. Na pasta
mobile execute `npm ci` e `npx expo start -c`. Recompile development builds nativos.
Reinicie a API. Estas mudanças não exigem nova migração de banco.
