import React, { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { useFinance } from "../stores/finance";
import {
  Budget,
  Goal,
  Contribution,
  money,
  month,
  isoDate,
} from "../lib/types";
import {
  BudgetForm,
  GoalForm,
  ContributionForm,
} from "../components/FinanceForms";
import {
  Button,
  Card,
  Confirm,
  Empty,
  ErrorBox,
  Field,
  Progress,
  Sheet,
  styles,
} from "../components/ui";
function Contributions({ goal, onClose }: { goal: Goal; onClose: () => void }) {
  const [items, setItems] = useState<Contribution[]>([]),
    [error, setError] = useState<string | null>(null),
    [remove, setRemove] = useState<Contribution | null>(null),
    [more, setMore] = useState(false);
  const load = async (offset = 0) => {
    try {
      const rows = await api<Contribution[]>(
        `/goals/${goal.id}/contributions?offset=${offset}`,
      );
      setItems((old) => (offset ? [...old, ...rows] : rows));
      setMore(rows.length === 100);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  return (
    <Sheet title="Aportes registrados" onClose={onClose}>
      <Text style={styles.h2}>{goal.title}</Text>
      <ErrorBox message={error} />
      {items.map((c) => (
        <Card key={c.id}>
          <Text style={styles.body}>
            {money(c.amount_cents)} · {c.on_date}
          </Text>
          <Button
            label="Remover aporte"
            secondary
            onPress={() => setRemove(c)}
          />
        </Card>
      ))}
      {!items.length ? (
        <Text style={styles.muted}>Nenhum aporte carregado.</Text>
      ) : null}
      {more ? (
        <Button
          label="Carregar mais"
          secondary
          onPress={() => load(items.length)}
        />
      ) : null}
      {remove ? (
        <Confirm
          message="Remover este aporte reduz a reserva da meta e devolve o valor ao saldo disponível registrado."
          onClose={() => setRemove(null)}
          onConfirm={async () => {
            await api(`/contributions/${remove.id}`, "DELETE");
            await load();
            await useFinance.getState().load();
          }}
        />
      ) : null}
    </Sheet>
  );
}
export function Plans() {
  const { budgets, goals, report, categories } = useFinance();
  const [period, setPeriod] = useState(month().slice(0, 7));
  const [selectedMonth, setSelectedMonth] = useState(month());
  const [otherBudgets, setOtherBudgets] = useState<Budget[]>([]);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const [periodBusy, setPeriodBusy] = useState(false);
  const refreshPeriod = async () => {
    setPeriodBusy(true);
    setPeriodError(null);
    try {
      const date = isoDate(period + "-01");
      const rows = await api<Budget[]>("/budgets?month=" + date);
      setOtherBudgets(rows);
      setSelectedMonth(date);
    } catch (e) {
      setPeriodError((e as Error).message);
    } finally {
      setPeriodBusy(false);
    }
  };
  const visibleBudgets = selectedMonth === month() ? budgets : otherBudgets;
  const [budget, setBudget] = useState<Budget | null | undefined>(undefined),
    [goal, setGoal] = useState<Goal | null | undefined>(undefined),
    [contribute, setContribute] = useState<Goal | null>(null),
    [history, setHistory] = useState<Goal | null>(null),
    [remove, setRemove] = useState<{ path: string; message: string } | null>(
      null,
    );
  return (
    <View style={styles.stack}>
      <Text style={styles.title}>Planos que crescem</Text>
      <Text style={styles.muted}>
        Limites para o mês. Objetivos para o que vem depois.
      </Text>
      <View style={styles.row}>
        <Text style={[styles.h2, { flex: 1 }]}>
          Orçamentos · {selectedMonth.slice(0, 7)}
        </Text>
        <Button label="＋ Limite" secondary onPress={() => setBudget(null)} />
      </View>
      <Field
        label="Consultar mês (AAAA-MM)"
        value={period}
        onChangeText={setPeriod}
        maxLength={7}
      />
      <Button
        label="Consultar orçamentos"
        secondary
        busy={periodBusy}
        onPress={refreshPeriod}
      />
      <ErrorBox message={periodError} />
      {visibleBudgets.length ? (
        visibleBudgets.map((b) => {
          const progress = report?.budgets.find((r) => r.id === b.id);
          return (
            <Card key={b.id}>
              <Text style={styles.h2}>
                {b.category === "total"
                  ? "Todos os gastos"
                  : categories.find((c) => c.id === b.category)?.label}
              </Text>
              <Text style={styles.body}>Limite de {money(b.limit_cents)}</Text>
              {progress ? (
                <>
                  <Progress
                    label="Uso do orçamento"
                    value={(progress.spent_cents / b.limit_cents) * 100}
                  />
                  <Text style={styles.muted}>
                    {money(progress.remaining_cents)} restantes até a data do
                    relatório
                  </Text>
                </>
              ) : null}
              <View style={styles.row}>
                <Button label="Editar" secondary onPress={() => setBudget(b)} />
                <Button
                  label="Excluir"
                  secondary
                  onPress={() =>
                    setRemove({
                      path: `/budgets/${b.id}`,
                      message:
                        "Excluir este limite não remove seus lançamentos.",
                    })
                  }
                />
              </View>
            </Card>
          );
        })
      ) : (
        <Empty
          title="Comece pelo que faz sentido"
          detail="Você pode definir um limite geral ou escolher categorias específicas."
        />
      )}
      <View style={styles.row}>
        <Text style={styles.h2}>Seus objetivos</Text>
        <Button label="＋ Objetivo" secondary onPress={() => setGoal(null)} />
      </View>
      {goals.length ? (
        goals.map((g) => {
          const progress = report?.goals.find((r) => r.id === g.id);
          return (
            <Card key={g.id} color="#EDF0D8">
              <Text style={styles.h2}>{g.title}</Text>
              {g.motivation ? (
                <Text style={styles.body}>{g.motivation}</Text>
              ) : null}
              <Text style={styles.muted}>
                Até {g.deadline.split("-").reverse().join("/")} · meta{" "}
                {money(g.target_cents)}
              </Text>
              <Progress
                label="Progresso da meta"
                value={((progress?.saved_cents || 0) / g.target_cents) * 100}
              />
              <Text style={styles.body}>
                {money(progress?.saved_cents || 0)} reservados
              </Text>
              <Button
                label="Registrar aporte"
                onPress={() => setContribute(g)}
              />
              <View style={[styles.row, { flexWrap: "wrap" }]}>
                <Button label="Editar" secondary onPress={() => setGoal(g)} />
                <Button
                  label="Aportes"
                  secondary
                  onPress={() => setHistory(g)}
                />
                <Button
                  label="Excluir"
                  secondary
                  onPress={() =>
                    setRemove({
                      path: `/goals/${g.id}`,
                      message:
                        "A meta só pode ser excluída após remover seus aportes.",
                    })
                  }
                />
              </View>
            </Card>
          );
        })
      ) : (
        <Empty
          title="Dê nome ao seu próximo passo"
          detail="Uma reserva, uma viagem, um curso. Defina o valor e o prazo para acompanhar seu avanço."
        />
      )}
      {budget !== undefined ? (
        <BudgetForm
          initialMonth={selectedMonth}
          budget={budget || undefined}
          onClose={() => {
            setBudget(undefined);
            void refreshPeriod();
          }}
        />
      ) : null}
      {goal !== undefined ? (
        <GoalForm goal={goal || undefined} onClose={() => setGoal(undefined)} />
      ) : null}
      {contribute ? (
        <ContributionForm
          goal={contribute}
          onClose={() => setContribute(null)}
        />
      ) : null}
      {history ? (
        <Contributions goal={history} onClose={() => setHistory(null)} />
      ) : null}
      {remove ? (
        <Confirm
          message={remove.message}
          onClose={() => setRemove(null)}
          onConfirm={async () => {
            await api(remove.path, "DELETE");
            await useFinance.getState().load();
            await refreshPeriod();
          }}
        />
      ) : null}
    </View>
  );
}
