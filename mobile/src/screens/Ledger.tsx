import { StatementImport } from "../components/StatementImport";
import React, { useState } from "react";
import { Text, View } from "react-native";
import {
  Button,
  Card,
  Choices,
  Confirm,
  Empty,
  Field,
  styles,
  colors,
} from "../components/ui";
import { EntryForm } from "../components/FinanceForms";
import { useFinance } from "../stores/finance";
import { Entry, Movement, money } from "../lib/types";
import { api } from "../lib/api";
export function Ledger() {
  const { entries, categories, more, loading, loadMore } = useFinance();
  const [filter, setFilter] = useState("all"),
    [search, setSearch] = useState(""),
    [edit, setEdit] = useState<Entry | null>(null),
    [remove, setRemove] = useState<Movement | null>(null);
  const filtered = entries.filter(
    (e) =>
      (filter === "all" || e.kind === filter) &&
      `${e.description} ${categories.find((c) => c.id === e.category)?.label}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <View style={styles.stack}>
      <Text style={styles.title}>Seu dia a dia</Text>
      <StatementImport />
      <Text style={styles.muted}>
        Lançamentos carregados, do mais recente ao mais antigo.
      </Text>
      <Choices
        items={[
          { id: "all", label: "Todos" },
          { id: "expense", label: "Despesas" },
          { id: "income", label: "Receitas" },
          { id: "contribution", label: "Aportes" },
        ]}
        value={filter}
        onChange={setFilter}
      />
      <Field
        label="Buscar nos lançamentos carregados"
        value={search}
        onChangeText={setSearch}
        placeholder="Categoria ou descrição"
      />
      {filtered.length ? (
        filtered.map((e) => (
          <Card key={`${e.kind}-${e.id}`}>
            <View style={styles.row}>
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={styles.h2}>
                  {e.kind === "contribution" ? "Aporte para objetivo" :
                    categories.find((c) => c.id === e.category)?.label || e.category}
                </Text>
                <Text style={styles.muted}>
                  {e.on_date.split("-").reverse().join("/")} ·{" "}
                  {e.description || "Sem descrição"}
                </Text>
              </View>
              <Text
                style={{
                  fontSize: 17,
                  fontWeight: "700",
                  color: e.kind === "income" ? colors.green : colors.ink,
                }}
              >
                {e.kind === "income" ? "+" : "−"} {money(e.amount_cents)}
              </Text>
            </View>
            <View style={styles.row}>
              {e.kind !== "contribution" ? <Button label="Editar" secondary onPress={() => setEdit(e)} /> : null}
              <Button label="Excluir" secondary onPress={() => setRemove(e)} />
            </View>
          </Card>
        ))
      ) : (
        <Empty
          title="Nenhum lançamento aqui"
          detail="Registre uma receita ou despesa, ou ajuste sua busca."
        />
      )}
      {more ? (
        <Button
          label="Carregar mais"
          busy={loading}
          secondary
          onPress={loadMore}
        />
      ) : null}
      {edit ? <EntryForm entry={edit} onClose={() => setEdit(null)} /> : null}
      {remove ? (
        <Confirm
          message={remove.kind === "contribution" ? "Remover o aporte devolve o valor ao saldo disponível e reduz a reserva do objetivo." : "Esta ação remove o lançamento e altera os próximos cálculos do relatório."}
          onClose={() => setRemove(null)}
          onConfirm={async () => {
            await api(`/${remove.kind === "contribution" ? "contributions" : "entries"}/${remove.id}`, "DELETE");
            await useFinance.getState().load();
          }}
        />
      ) : null}
    </View>
  );
}
