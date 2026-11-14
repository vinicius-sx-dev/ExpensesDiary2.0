# Modelo financeiro

| Conceito | Entrada | Regra |
| --- | --- | --- |
| Receita | valor, categoria, data | entrada realizada, não previsão de salário |
| Despesa | valor, categoria, data, descrição, meio de pagamento, essencial | uma linha por gasto; não aceitar saldo ou user_id do cliente |
| Orçamento | mês, categoria ou `total`, limite | limite positivo; único por usuário/mês/categoria |
| Objetivo | título, motivação | propósito pessoal, sem julgamento automático |
| Meta | valor-alvo e prazo do objetivo | progresso calculado pelos aportes; até 100 objetivos |
| Aporte | objetivo próprio, valor e data | reserva declarada; não conta como despesa e não move dinheiro |

Dinheiro é representado em **centavos inteiros**. R$ 25,50 = `2550`. Floats, strings monetárias, booleanos, negativos e valores acima de R$ 100 milhões por lançamento são rejeitados pela API. O app converte a vírgula decimal sem aritmética de ponto flutuante.

`request_id` é um UUID estável para evitar duplicatas em reenvios. Reutilizar a mesma chave com outro conteúdo gera 409. Edição preserva a chave. Conflitos simultâneos podem retornar 409; consulte a lista antes de repetir com outra chave.

A data é a do gasto efetivamente ocorrido. Não há recorrência automática, parcelamento, contas bancárias ou conciliação neste MVP. Para compras no cartão, registre a compra uma vez; não registre o pagamento da fatura novamente. Despesas com quitação de dívidas antigas precisam ser classificadas sem duplicar compras já lançadas.

A categoria `total` compara todas as despesas com o limite geral. Os demais limites são comparações independentes: não são somados ao total nem exigem que todas as categorias tenham um orçamento. A definição de “essencial” pertence ao usuário. O app não presume que restaurante seja impulso nem que uma consulta possa ser cortada.

## Relatório

- Semana de segunda a domingo, com fim limitado ao dia atual se ainda estiver em andamento.
- Receitas, despesas e reservas usam exatamente o intervalo semanal.
- Orçamento mensal usa o acumulado desde o início do respectivo mês até o fim do intervalo. Se a semana atravessar dois meses, ambos aparecem separadamente. Não dividir um orçamento mensal por quatro.
- Sem orçamento definido, a situação é “sem referência”, não “dentro do orçamento”.
- Fluxo líquido = receitas registradas − despesas registradas; não é saldo bancário.
- Fluxo não reservado = fluxo líquido − aportes declarados na semana. Pode ser negativo: reservas podem usar dinheiro de meses anteriores.
- Reserva semanal necessária = restante da meta / semanas até o prazo, arredondada para cima em centavos. Meta vencida fica identificada; meta ultrapassada é concluída.
- A soma das necessidades semanais ajuda a avaliar o esforço conjunto. Uma semana sem salário registrado não prova inviabilidade: o app não conhece renda recorrente, saldo inicial nem completude dos lançamentos.
- Aportes históricos contam até o fim da semana consultada. Metas e orçamentos usam as definições atuais; não há versionamento dessas definições. Retratos já salvos preservam os números do momento da gravação.

A API é a autoridade para cálculos, validação e autorização. A IA recebe somente agregados calculados, sem texto livre do usuário, e produz comentários validados. Não determina números oficiais, não executa ações, não possui histórico global e não altera os dados.

## Categorias

O catálogo completo e os identificadores estáveis estão em `app/categories.py` e `GET /categories`. Grupos: alimentação, moradia, transporte, saúde, educação, cuidados pessoais, lazer, pets, família/compromissos. Exemplos: restaurante, mercado, gasolina, consulta médica, exames, terapia, condomínio, streaming e veterinário. “Outros” existe para exceções; a descrição ajuda o usuário a revisar depois, mas não é enviada à IA.
