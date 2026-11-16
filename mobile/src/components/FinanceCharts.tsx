import React from "react";
import { Text, View } from "react-native";
import { Card, colors, styles } from "./ui";
import { Category, Report, money } from "../lib/types";

function Bar({label, amount, maximum, color}: {label: string; amount: number; maximum: number; color: string}) {
  const percent = maximum > 0 ? Math.max(0, Math.min(100, amount / maximum * 100)) : 0;
  return <View style={{gap: 5}} accessibilityLabel={label + ": " + money(amount)}>
    <Text style={styles.body}>{label} · {money(amount)}</Text>
    <View style={{height: 14, borderRadius: 7, backgroundColor: colors.line, overflow: "hidden"}}>
      <View style={{height: 14, width: `${percent}%`, backgroundColor: color}} />
    </View>
  </View>;
}
export function FinanceCharts({report: r, categories}: {report: Report; categories: Category[]}) {
  const name = (id: string) => categories.find(c => c.id === id)?.label || id;
  const total = r.income_cents + r.expense_cents;
  const maximum = Math.max(r.income_cents, r.expense_cents);
  const dailyMax = Math.max(0, ...(r.daily || []).flatMap(d => [d.income_cents, d.expense_cents]));
  return <View style={styles.stack}>
    <Card>
      <Text style={styles.h2}>Receitas e despesas</Text>
      <Text style={styles.muted}>{r.week_start} a {r.week_end} · Aportes não são despesas de consumo.</Text>
      <Bar label="Receitas" amount={r.income_cents} maximum={maximum} color={colors.green} />
      <Bar label="Despesas" amount={r.expense_cents} maximum={maximum} color={colors.danger} />
      <Text style={styles.h2}>Proporção das movimentações</Text>
      {total ? <>
        <View style={{flexDirection: "row", height: 22, borderRadius: 8, overflow: "hidden"}}>
          <View style={{flex: r.income_cents, backgroundColor: colors.green}} />
          <View style={{flex: r.expense_cents, backgroundColor: colors.danger}} />
        </View>
        <Text style={styles.body}>Receitas {(r.income_cents / total * 100).toFixed(1)}% · Despesas {(r.expense_cents / total * 100).toFixed(1)}% do total movimentado.</Text>
        <Text style={styles.muted}>{r.income_cents > 0 ? `Despesas equivalem a ${(r.expense_cents / r.income_cents * 100).toFixed(1)}% das receitas registradas.` : "Sem receitas registradas: razão despesas/receitas indisponível."}</Text>
      </> : <Text style={styles.muted}>Sem movimentações no período.</Text>}
    </Card>
    <Card>
      <Text style={styles.h2}>Distribuição dos gastos</Text>
      {r.categories.map(c => <View key={c.category} style={{gap: 4}}>
        <Bar label={name(c.category)} amount={c.amount_cents} maximum={r.expense_cents} color={colors.danger} />
        <Text style={styles.muted}>{r.expense_cents ? (c.amount_cents / r.expense_cents * 100).toFixed(1) : "0.0"}% das despesas</Text>
      </View>)}
      {!r.categories.length && <Text style={styles.muted}>Sem despesas no período.</Text>}
      <Text style={styles.h2}>Distribuição das receitas</Text>
      {(r.income_categories || []).map(c => <Bar key={c.category} label={name(c.category)} amount={c.amount_cents} maximum={r.income_cents} color={colors.green} />)}
      {!r.income_categories && <Text style={styles.muted}>Consulte novamente a semana para atualizar este detalhamento.</Text>}
      {r.income_categories?.length === 0 && <Text style={styles.muted}>Sem receitas no período.</Text>}
    </Card>
    {!!r.daily?.length && <Card>
      <Text style={styles.h2}>Evolução diária</Text>
      {r.daily.map(d => <View key={d.date} style={{gap: 6}}>
        <Text style={styles.body}>{d.date.split("-").reverse().join("/")}</Text>
        <Bar label="Receitas do dia" amount={d.income_cents} maximum={dailyMax} color={colors.green} />
        <Bar label="Despesas do dia" amount={d.expense_cents} maximum={dailyMax} color={colors.danger} />
      </View>)}
    </Card>}
  </View>;
}
