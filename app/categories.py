# Stable slugs are API identifiers; labels can evolve without corrupting history.
GROUPS = {
    "Alimentação": [
        ("mercado", "Mercado"),
        ("restaurante", "Restaurante"),
        ("delivery", "Delivery"),
        ("padaria", "Padaria"),
        ("cafe", "Café e lanches"),
    ],
    "Moradia": [
        ("aluguel", "Aluguel"),
        ("condominio", "Condomínio"),
        ("energia", "Energia"),
        ("agua", "Água"),
        ("gas", "Gás"),
        ("internet", "Internet"),
        ("manutencao_casa", "Manutenção da casa"),
        ("moveis", "Móveis e utensílios"),
    ],
    "Transporte": [
        ("gasolina", "Gasolina / combustível"),
        ("transporte_publico", "Transporte público"),
        ("aplicativo", "Transporte por aplicativo"),
        ("estacionamento", "Estacionamento"),
        ("pedagio", "Pedágio"),
        ("manutencao_veiculo", "Manutenção do veículo"),
        ("seguro_veiculo", "Seguro do veículo"),
    ],
    "Saúde": [
        ("consulta_medica", "Consulta médica"),
        ("dentista", "Dentista"),
        ("exames", "Exames"),
        ("medicamentos", "Medicamentos"),
        ("plano_saude", "Plano de saúde"),
        ("terapia", "Terapia"),
    ],
    "Educação": [
        ("mensalidade", "Mensalidade escolar"),
        ("cursos", "Cursos"),
        ("livros", "Livros"),
        ("material_escolar", "Material escolar"),
    ],
    "Cuidados pessoais": [
        ("roupas", "Roupas e calçados"),
        ("higiene", "Higiene"),
        ("beleza", "Beleza"),
        ("academia", "Academia e esporte"),
    ],
    "Lazer": [
        ("streaming", "Streaming"),
        ("jogos", "Jogos"),
        ("eventos", "Shows e eventos"),
        ("viagem", "Viagem"),
        ("hobbies", "Hobbies"),
    ],
    "Pets": [
        ("racao", "Ração"),
        ("veterinario", "Veterinário"),
        ("banho_tosa", "Banho e tosa"),
        ("acessorios_pet", "Acessórios para pets"),
    ],
    "Família e compromissos": [
        ("creche", "Creche"),
        ("dependentes", "Cuidados com dependentes"),
        ("presentes", "Presentes"),
        ("doacoes", "Doações"),
        ("impostos", "Impostos e taxas"),
        ("juros", "Juros e tarifas"),
        ("dividas", "Pagamento de dívidas"),
        ("seguros", "Outros seguros"),
        ("telefonia", "Telefonia"),
        ("servicos_digitais", "Serviços digitais"),
        ("outros", "Outros gastos"),
    ],
}
EXPENSE_CATEGORIES = {slug for items in GROUPS.values() for slug, _ in items}
INCOME_CATEGORIES = {"salario", "freelance", "beneficios", "outras_receitas"}


def catalog():
    return [
        {"id": slug, "label": label, "group": group, "kind": "expense"}
        for group, items in GROUPS.items()
        for slug, label in items
    ] + [
        {"id": slug, "label": label, "group": "Receitas", "kind": "income"}
        for slug, label in [
            ("salario", "Salário"),
            ("freelance", "Freelance"),
            ("beneficios", "Benefícios"),
            ("outras_receitas", "Outras receitas"),
        ]
    ]
