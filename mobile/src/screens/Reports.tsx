import React, { useEffect, useState } from "react";
import { Text, View } from "react-native";
import {
  Button,
  Card,
  ErrorBox,
  Field,
  Progress,
  styles,
} from "../components/ui";
import { useFinance } from "../stores/finance";
import { api } from "../lib/api";
import { Report, Insight, isoDate, money } from "../lib/types";
import { FinanceCharts } from "../components/FinanceCharts";
import { exportReportPdf } from "../lib/reportPdf";

export function Reports({ onOpenSaved }: { onOpenSaved: () => void }) {
  const current = useFinance((s) => s.report),
    categories = useFinance((s) => s.categories);
  const [date, setDate] = useState(current?.week_start || ""),
    [report, setReport] = useState<Report | null>(null),
    [insight, setInsight] = useState<Insight | null>(null),
    [history, setHistory] = useState<Report[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState("");
  const r = report || current;
  useEffect(() => { if (!date && current) setDate(current.week_start); }, [current, date]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <View style={styles.stack}>
      <Text style={styles.title}>Uma pausa para olhar</Text>
      <Text style={styles.muted}>
        Números calculados pelo app, comparados com o que você planejou.
      </Text>
      <Field
        label="Início da semana · segunda-feira (AAAA-MM-DD)"
        value={date}
        onChangeText={setDate}
      />
      <Button
        label="Consultar semana"
        busy={busy}
        onPress={() =>
          run(async () => {
            setReport(
              await api<Report>("/reports/weekly?week_start=" + isoDate(date)),
            );
            setInsight(null);
          })
        }
      />
      <ErrorBox message={error} />
      {message ? (
        <Text accessibilityRole="alert" style={styles.body}>
          {message}
        </Text>
      ) : null}
      {r ? (
        <>
          <Button
            label="Exportar PDF do relatório exibido"
            secondary
            busy={busy}
            onPress={() => run(async () => {
              await exportReportPdf(r, categories, insight);
              setMessage("PDF exportado ou encaminhado ao compartilhamento.");
            })}
          />
          <FinanceCharts report={r} categories={categories} />
          <Card color="#E8EBCF">
            <Text style={styles.h2}>
              {r.week_start.split("-").reverse().join("/")} —{" "}
              {r.week_end.split("-").reverse().join("/")}
            </Text>
            <Text style={styles.muted}>
              {r.partial ? "Semana em andamento" : "Semana encerrada"}
            </Text>
            {[
              ["Receitas registradas", r.income_cents],
              ["Despesas registradas", r.expense_cents],
              ["Fluxo líquido", r.net_cents],
              ["Aportes na semana", r.reserved_cents],
              ["Fluxo após aportes na semana", r.unreserved_flow_cents],
              ...(r.available_cents !== undefined ? [["Saldo disponível até esta data", r.available_cents]] : []),
            ].map(([label, value]) => (
              <View key={label} style={styles.row}>
                <Text style={[styles.body, { flex: 1 }]}>{label}</Text>
                <Text style={[styles.body, { fontWeight: "700" }]}>
                  {money(Number(value))}
                </Text>
              </View>
            ))}
          </Card>
          <Text style={styles.h2}>Onde seu dinheiro passou</Text>
          {r.categories.map((c) => (
            <Card key={c.category}>
              <View style={styles.row}>
                <Text style={[styles.body, { flex: 1 }]}>
                  {categories.find((x) => x.id === c.category)?.label ||
                    c.category}
                </Text>
                <Text style={styles.h2}>{money(c.amount_cents)}</Text>
              </View>
              {(c.essential_cents || 0) > 0 ? (
                <Text style={styles.muted}>
                  {money(c.essential_cents || 0)} marcados por você como
                  essenciais
                </Text>
              ) : null}
              <Progress
                label="Participação nas despesas"
                value={
                  r.expense_cents ? (c.amount_cents / r.expense_cents) * 100 : 0
                }
              />
            </Card>
          ))}
          {!r.categories.length ? (
            <Text style={styles.body}>
              Sem despesas registradas nesta semana.
            </Text>
          ) : null}
          <Text style={styles.h2}>Seus limites, no contexto do mês</Text>
          {r.budgets.map((b) => (
            <Card key={b.id}>
              <Text style={styles.h2}>
                {b.category === "total"
                  ? "Todos os gastos"
                  : categories.find((c) => c.id === b.category)?.label}{" "}
                · {b.month.slice(0, 7)}
              </Text>
              <Text style={styles.body}>
                {money(b.spent_cents)} de {money(b.limit_cents)}
              </Text>
              <Text style={styles.body}>
                {b.remaining_cents < 0
                  ? `Acima do limite em ${money(-b.remaining_cents)}`
                  : `Dentro do limite · restam ${money(b.remaining_cents)}`}
              </Text>
            </Card>
          ))}
          {!r.budgets.length ? (
            <Text style={styles.muted}>
              Sem orçamento definido para este período. Isso não significa estar
              dentro do orçamento.
            </Text>
          ) : null}
          <Card color="#F8D8B6">
            <Text style={styles.h2}>O próximo passo dos objetivos</Text>
            <Text style={styles.body}>
              Reserva semanal estimada: {money(r.required_weekly_cents)}
            </Text>
            {r.goals.map((g) => (
              <Text key={g.id} style={styles.body}>
                {g.title}: {money(g.saved_cents)} de {money(g.target_cents)} ·{" "}
                {g.status === "completed"
                  ? "Concluído"
                  : g.status === "overdue"
                    ? "Prazo vencido"
                    : `${money(g.required_weekly_cents)} por semana`}
              </Text>
            ))}
            <Text style={styles.muted}>{r.note}</Text>
          </Card>
          <Button
            label="Salvar retrato e exportar PDF"
            secondary
            busy={busy}
            onPress={() =>
              run(async () => {
                const saved = await api<Report>("/reports/weekly?week_start=" + r.week_start, "POST");
                setReport(saved);
                setInsight(null);
                setHistory((rows) =>
                  [saved, ...rows.filter((row) => row.week_start !== saved.week_start)],
                );
                setMessage(
                  "Retrato semanal salvo.",
                );
                try {
                  await exportReportPdf(saved, categories);
                  setMessage("Retrato salvo. Exportação de PDF concluída ou encaminhada ao compartilhamento.");
                } catch {
                  throw new Error("Retrato salvo, mas não foi possível exportar o PDF. Use Exportar PDF para tentar novamente. Confira se as dependências nativas estão instaladas.");
                }
              })
            }
          />
          <Card>
            <Text style={styles.h2}>Uma segunda perspectiva</Text>
            <Text style={styles.muted}>
              Ao solicitar, você envia totais por categoria, limites e progresso
              de metas para a Groq. Nomes, e-mail e descrições não são enviados.
              Os comentários podem conter erros e não alteram seus dados.
            </Text>
            <Button
              label="Enviar totais e pedir comentários à IA"
              busy={busy}
              onPress={() =>
                run(async () => {
                  setInsight(
                    await api<Insight>(
                      "/reports/weekly/insights?week_start=" + r.week_start,
                      "POST",
                    ),
                  );
                })
              }
            />
            {insight ? (
              <>
                <Text style={styles.body}>{insight.summary}</Text>
                {insight.suggestions.map((s, i) => (
                  <Text key={i} style={styles.body}>
                    • {s}
                  </Text>
                ))}
              </>
            ) : null}
          </Card>
        </>
      ) : null}
      <Button
        label="Ver últimos retratos salvos"
        secondary
        busy={busy}
        onPress={() =>
          run(async () => {
            const rows = await api<Report[]>("/reports/history");
            setHistory(rows);
            if (!rows.length) setMessage("Nenhum retrato salvo ainda.");
          })
        }
      />
      {history.map((h) => (
        <Button
          key={h.week_start}
          label={`Abrir ${h.week_start}`}
          secondary
          busy={busy}
          onPress={() => run(async () => {
            setReport(h);
            setDate(h.week_start);
            setInsight(null);
            setMessage(
              "Exibindo retrato salvo; consulte a semana para recalcular os dados atuais.",
            );
            onOpenSaved();
            await exportReportPdf(h, categories);
          })}
        />
      ))}
    </View>
  );
}
