# Auditoria de importações e aprendizado — 16/11/2026

Base: `feat/multi-bank-parsers`, commit `839fa74328b0d4d02a7dff3de7f6c16643e34fcc`.
Correções: `fix/import-learning-reports`. Sem migração nova.

## Achados e correções

| Prioridade | Achado | Correção |
| --- | --- | --- |
| Alta | Confirmação impunha outros/outras_receitas, sem revisão da categoria | Categoria, essencialidade e contexto revisáveis por item; validação servidor por tipo e índice |
| Alta | Não havia memória de classificações pessoais | Sugestões por estabelecimento normalizado e direção, usando somente escolhas explícitas do próprio usuário; conflitos abstêm |
| Alta | Duas prévias simultâneas podiam repetir movimentos | Rechecagem sob lock da carteira na confirmação; resposta 409 e aceite explícito para possíveis duplicatas |
| Alta | Contextos importados sem revisão podiam ser tratados como gastos opcionais | Itens novos não revisados entram nos totais, mas não nas recomendações de corte nem no treinamento |
| Média | Envio nativo dependia de implementação compatível de FormData | Envio de bytes no Android/iOS com formato e instituição explícitos; multipart web mantido |
| Alta | PicPay guardado/resgatado entrava selecionado como consumo/renda | Marcação explícita de movimentação interna e seleção inicial desativada com aviso de impacto nos totais |
| Média | Sem gráficos consolidados e de evolução diária | Gráficos em Hoje/Semana; agregação diária e receitas por categoria no servidor, isolada por usuário |
| Média | PDF pouco visível no fim da tela; temporário persistia | Botão no início, barras e detalhamentos no PDF; limpeza do temporário nativo |
| Baixa | Campo de semana ficava vazio se o relatório chegasse depois da montagem | Inicialização quando o carregamento termina |
| Preventiva | Limite padrão de corpo não comportava 2.000 classificações | Teto de 512 KiB somente para confirmação de importação; limite de 2.000 itens permanece |

## Como funciona

Na prévia, revise categoria, contexto e essencialidade usando **Revisar categoria**. Confirmar categoria ou alterar seus campos é uma escolha explícita. A confirmação final salva somente as revisões de linhas selecionadas. Desmarcar uma linha impede que sua revisão seja usada.

Sem evidência, o app mantém a categoria genérica e mostra **A revisar**. Não infere salário, impulsividade, essencialidade ou estabelecimentos a partir de nomes de pessoas em Pix. Há apenas dicas conservadoras para nomes explícitos de supermercados, padarias, restaurantes e farmácias. Dicas não revisadas não ensinam o classificador.

Aprendizado é uma memória determinística de classificações, não treinamento de modelo de IA. Consulta os últimos 5.000 lançamentos do usuário. Considera somente registros manuais com contexto ou importações explicitamente revisadas; separa receitas e despesas, mantém pontuação/números do estabelecimento e se abstém diante de categorias conflitantes. Edição e exclusão afetam novas sugestões; prévias já abertas preservam a sugestão exibida originalmente. Nenhum estabelecimento é enviado a serviços externos.

Lançamentos antigos podem ser corrigidos em **Diário → editar lançamento**. A edição passa a contar como revisão explícita e preserva a origem do registro. Não há recategorização silenciosa do histórico nem dos retratos de relatório salvos. Consulte novamente a semana para recalcular o relatório.

## Limites e pendências da auditoria

- Possível duplicata usa data, direção e valor; pagamentos legítimos iguais podem coincidir. Por isso há revisão, sem exclusão silenciosa.
- Dinheiro guardado/resgatado do PicPay começa desmarcado e identificado como movimentação interna. Transferências entre contas próprias e pagamento de fatura ainda exigem revisão manual e desmarcação para evitar dupla contagem de consumo/receitas. O livro atual não tem um modelo de transferências entre contas; esta mudança não inventa equivalência contábil.
- O suporte real dos layouts continua o documentado em STATEMENT_IMPORTS.md; não houve homologação universal de bancos.
- Arquivo parcialmente confirmado permanece marcado como confirmado. Para movimentos não selecionados, use lançamento manual ou outra exportação/período, revisando possíveis duplicatas.
- Ausência de estabelecimento impede memória por estabelecimento, mas a classificação manual continua contribuindo para categorias e padrões.
- O envio e a exportação nativos precisam de teste em aparelho Android/iOS. A CI cobre servidor, web, tipagem, Expo e testes de interface; não substitui esse teste.
- Não foi executada auditoria dinâmica contra produção nem teste de carga.

## Validação

Testes adicionados para aprendizado explícito, isolamento entre usuários/tipos, conflitos, exclusão/edição de exemplos, ausência de autoaprendizado, essencialidade, duplicatas confirmadas após abrir outra prévia, índices inválidos, categoria incompatível, 2.000 classificações e totais diários.
Playwright exercita revisão de categoria e confirma o corpo enviado, os gráficos e downloads PDF nas três larguras existentes.
Resultados de execução estão vinculados ao PR #3 e ao commit validado; ambiente local de execução indisponível nesta sessão.
