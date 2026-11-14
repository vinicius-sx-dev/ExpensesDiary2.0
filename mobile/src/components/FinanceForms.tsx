import React, { useState } from "react";
import { Text, View, Switch } from "react-native";
import * as Crypto from "expo-crypto";
import { api } from "../lib/api";
import {
  Budget,
  Entry,
  Goal,
  cents,
  inputMoney,
  isoDate,
  localDate,
  month,
} from "../lib/types";
import { useFinance } from "../stores/finance";
import { Button, Choices, ErrorBox, Field, Sheet, styles, colors } from "./ui";
function useSubmit(onClose: () => void) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  return {
    busy,
    error,
    run: async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
        await useFinance.getState().load();
        onClose();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Não foi possível salvar");
      } finally {
        setBusy(false);
      }
    },
  };
}
export function CategoryPicker({
  value,
  kind,
  onChange,
  total = false,
}: {
  value: string;
  kind: "expense" | "income";
  onChange: (id: string) => void;
  total?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);
  const categories = useFinance((s) => s.categories);
  const options = [
    ...(total
      ? [
          {
            id: "total",
            label: "Todos os gastos",
            group: "Limite geral",
            kind: "expense",
          },
        ]
      : []),
    ...categories,
  ].filter(
    (c) =>
      c.kind === kind &&
      `${c.label} ${c.group}`.toLowerCase().includes(search.toLowerCase()),
  );
  const selected = categories.find((c) => c.id === value);
  return (
    <View style={{ gap: 10 }}>
      <Text style={styles.body}>
        Categoria:{" "}
        {value === "total" ? "Todos os gastos" : selected?.label || "selecione"}
      </Text>
      <Field
        label="Buscar categoria"
        value={search}
        onChangeText={setSearch}
        placeholder="Mercado, saúde, gasolina…"
      />
      <Choices
        items={(expanded || search ? options : options.slice(0, 8)).map(
          (c) => ({ id: c.id, label: c.label }),
        )}
        value={value}
        onChange={onChange}
      />
      {!search && options.length > 8 ? (
        <Button
          secondary
          label={
            expanded ? "Mostrar menos categorias" : "Ver todas as categorias"
          }
          onPress={() => setExpanded(!expanded)}
        />
      ) : null}
      {options.length === 0 ? (
        <Text style={styles.muted}>Nenhuma categoria encontrada.</Text>
      ) : null}
    </View>
  );
}
export function EntryForm({
  entry,
  onClose,
}: {
  entry?: Entry;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<"expense" | "income">(
      entry?.kind || "expense",
    ),
    [category, setCategory] = useState(entry?.category || ""),
    [amount, setAmount] = useState(entry ? inputMoney(entry.amount_cents) : ""),
    [date, setDate] = useState(entry?.on_date || localDate()),
    [description, setDescription] = useState(entry?.description || ""),
    [essential, setEssential] = useState(entry?.essential || false),
    [payment, setPayment] = useState(entry?.payment_method || "pix"),
    [requestId] = useState(entry?.request_id || Crypto.randomUUID());
  const { busy, error, run } = useSubmit(onClose);
  return (
    <Sheet
      title={entry ? "Editar lançamento" : "Novo lançamento"}
      onClose={onClose}
    >
      <Choices
        items={[
          { id: "expense", label: "Despesa" },
          { id: "income", label: "Receita" },
        ]}
        value={kind}
        onChange={(k) => {
          setKind(k);
          setCategory("");
        }}
      />
      <Field
        label="Valor (R$)"
        value={amount}
        onChangeText={setAmount}
        keyboardType="decimal-pad"
        placeholder="0,00"
      />
      <Field
        label="Data (AAAA-MM-DD)"
        value={date}
        onChangeText={setDate}
        maxLength={10}
      />
      <CategoryPicker kind={kind} value={category} onChange={setCategory} />
      <Field
        label="Descrição · opcional"
        value={description}
        onChangeText={setDescription}
        maxLength={240}
      />
      <Text style={styles.body}>Forma de pagamento</Text>
      <Choices
        items={[
          { id: "pix", label: "Pix" },
          { id: "debit", label: "Débito" },
          { id: "credit", label: "Crédito" },
          { id: "cash", label: "Dinheiro" },
          { id: "transfer", label: "Transferência" },
          { id: "other", label: "Outra" },
        ]}
        value={payment}
        onChange={setPayment}
      />
      {kind === "expense" ? (
        <View style={styles.row}>
          <Text style={[styles.body, { flex: 1 }]}>Essencial para mim</Text>
          <Switch
            accessibilityLabel="Marcar despesa como essencial"
            value={essential}
            onValueChange={setEssential}
            trackColor={{ true: colors.green }}
          />
        </View>
      ) : null}
      <Text style={styles.muted}>
        No cartão, registre a compra uma vez. Não registre a fatura novamente
        como despesa.
      </Text>
      <ErrorBox message={error} />
      <Button
        busy={busy}
        label="Salvar lançamento"
        onPress={() =>
          run(() => {
            if (!category) throw new Error("Selecione uma categoria.");
            const on_date = isoDate(date);
            if (on_date > localDate())
              throw new Error("Registre apenas lançamentos já realizados.");
            return api(
              entry ? `/entries/${entry.id}` : "/entries",
              entry ? "PUT" : "POST",
              {
                request_id: requestId,
                kind,
                category,
                amount_cents: cents(amount),
                on_date,
                description,
                essential: kind === "expense" && essential,
                payment_method: payment,
              },
            );
          })
        }
      />
    </Sheet>
  );
}
export function BudgetForm({
  budget,
  initialMonth,
  onClose,
}: {
  budget?: Budget;
  initialMonth?: string;
  onClose: () => void;
}) {
  const [category, setCategory] = useState(budget?.category || "total"),
    [amount, setAmount] = useState(
      budget ? inputMoney(budget.limit_cents) : "",
    ),
    [period, setPeriod] = useState(
      (budget?.month || initialMonth || month()).slice(0, 7),
    );
  const { busy, error, run } = useSubmit(onClose);
  return (
    <Sheet
      title={budget ? "Editar orçamento" : "Defina um limite"}
      onClose={onClose}
    >
      <Text style={styles.body}>
        Quanto você quer gastar no mês? O limite geral e os limites por
        categoria são comparados separadamente.
      </Text>
      <Field
        label="Mês (AAAA-MM)"
        value={period}
        onChangeText={setPeriod}
        maxLength={7}
      />
      <Field
        label="Limite (R$)"
        value={amount}
        onChangeText={setAmount}
        keyboardType="decimal-pad"
      />
      <CategoryPicker
        kind="expense"
        value={category}
        onChange={setCategory}
        total
      />
      <ErrorBox message={error} />
      <Button
        label="Salvar orçamento"
        busy={busy}
        onPress={() =>
          run(() =>
            api(
              budget ? `/budgets/${budget.id}` : "/budgets",
              budget ? "PUT" : "POST",
              {
                month: isoDate(period + "-01"),
                category,
                limit_cents: cents(amount),
              },
            ),
          )
        }
      />
    </Sheet>
  );
}
export function GoalForm({
  goal,
  onClose,
}: {
  goal?: Goal;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(goal?.title || ""),
    [motivation, setMotivation] = useState(goal?.motivation || ""),
    [amount, setAmount] = useState(goal ? inputMoney(goal.target_cents) : ""),
    [deadline, setDeadline] = useState(goal?.deadline || "");
  const { busy, error, run } = useSubmit(onClose);
  return (
    <Sheet
      title={goal ? "Editar objetivo" : "Um novo objetivo"}
      onClose={onClose}
    >
      <Field
        label="O que você quer conquistar?"
        value={title}
        onChangeText={setTitle}
        placeholder="Minha reserva de emergência"
        maxLength={100}
      />
      <Field
        label="Por que isso importa? · opcional"
        value={motivation}
        onChangeText={setMotivation}
        maxLength={240}
        multiline
      />
      <Field
        label="Meta de valor (R$)"
        value={amount}
        onChangeText={setAmount}
        keyboardType="decimal-pad"
      />
      <Field
        label="Prazo (AAAA-MM-DD)"
        value={deadline}
        onChangeText={setDeadline}
        maxLength={10}
      />
      <Text style={styles.muted}>
        Objetivo é o que você quer alcançar. A meta é o valor e o prazo. Aportes
        mostram o quanto você realmente reservou.
      </Text>
      <ErrorBox message={error} />
      <Button
        label="Salvar objetivo"
        busy={busy}
        onPress={() =>
          run(() => {
            if (title.trim().length < 2)
              throw new Error("Dê um nome ao seu objetivo.");
            if (isoDate(deadline) < localDate())
              throw new Error("Escolha um prazo atual ou futuro.");
            return api(
              goal ? `/goals/${goal.id}` : "/goals",
              goal ? "PUT" : "POST",
              {
                title: title.trim(),
                motivation,
                target_cents: cents(amount),
                deadline,
              },
            );
          })
        }
      />
    </Sheet>
  );
}
export function ContributionForm({
  goal,
  onClose,
}: {
  goal: Goal;
  onClose: () => void;
}) {
  const [amount, setAmount] = useState(""),
    [date, setDate] = useState(localDate()),
    [requestId] = useState(Crypto.randomUUID());
  const { busy, error, run } = useSubmit(onClose);
  return (
    <Sheet title="Registrar uma reserva" onClose={onClose}>
      <Text style={styles.h2}>{goal.title}</Text>
      <Text style={styles.body}>
        O aporte sai do saldo disponível e fica reservado neste objetivo.
        Registre antes a origem do dinheiro em Receitas. Não lance o mesmo
        aporte como despesa. O app não movimenta sua conta bancária.
      </Text>
      <Field
        label="Valor reservado (R$)"
        value={amount}
        onChangeText={setAmount}
        keyboardType="decimal-pad"
      />
      <Field
        label="Data (AAAA-MM-DD)"
        value={date}
        onChangeText={setDate}
        maxLength={10}
      />
      <ErrorBox message={error} />
      <Button
        label="Registrar aporte"
        busy={busy}
        onPress={() =>
          run(() =>
            api(`/goals/${goal.id}/contributions`, "POST", {
              request_id: requestId,
              amount_cents: cents(amount),
              on_date: isoDate(date),
            }),
          )
        }
      />
    </Sheet>
  );
}
