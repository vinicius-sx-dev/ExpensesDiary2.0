import React from "react";
import { Text, View, useWindowDimensions } from "react-native";
import {
  Button,
  Card,
  Empty,
  Progress,
  styles,
  colors,
} from "../components/ui";
import { FinanceCharts } from "../components/FinanceCharts";
import { Garden } from "../components/Garden";
import { useFinance } from "../stores/finance";
import { money } from "../lib/types";
export function Home({
  onAdd,
  onPlans,
  onReport,
}: {
  onAdd: () => void;
  onPlans: () => void;
  onReport: () => void;
}) {
  const { report, categories } = useFinance();
  const { width } = useWindowDimensions();
  return (
    <View style={styles.stack}>
      <View style={{ gap: 8 }}>
        <Text
          style={{
            color: colors.green,
            fontSize: 12,
            fontWeight: "800",
            letterSpacing: 2,
          }}
        >
          SEU DIÁRIO FINANCEIRO
        </Text>
        <Text style={styles.title}>
          Pequenos cuidados.{"\n"}Novas possibilidades.
        </Text>
        <Text style={styles.muted}>
          Acompanhe o presente e dê espaço aos seus planos.
        </Text>
      </View>
      <Garden />
      <Card color={colors.green}>
        <Text style={{ color: "#E5ECD5", fontSize: 14 }}>
          Saldo disponível registrado
        </Text>
        <Text
          style={{
            color: colors.white,
            fontSize: width < 360 ? 30 : 40,
            fontWeight: "800",
          }}
        >
          {report ? money(report.available_cents ?? report.unreserved_flow_cents) : "Indisponível"}
        </Text>
        <Text style={{ color: "#E5ECD5", fontSize: 13 }}>
          Histórico de receitas menos despesas e aportes
        </Text>
        <View style={styles.row}>
          <Text style={{ color: colors.lime, flex: 1 }}>
            Entrou na semana{"\n"}
            {money(report?.income_cents || 0)}
          </Text>
          <Text style={{ color: "#FBD1E4", flex: 1 }}>
            Despesas na semana{"\n"}
            {money(report?.expense_cents || 0)}
          </Text>
        </View>
      </Card>
      <Button label="＋ Registrar lançamento" onPress={onAdd} />
      <View style={[styles.row, { alignItems: "stretch", flexWrap: "wrap" }]}>
        <View style={{ flex: 1, minWidth: 140 }}>
          <Card color={colors.lime}>
            <Text style={styles.muted}>Reservado na semana</Text>
            <Text style={styles.h2}>{money(report?.reserved_cents || 0)}</Text>
            <Text style={styles.muted}>Cada passo conta.</Text>
          </Card>
        </View>
        <View style={{ flex: 1, minWidth: 140 }}>
          <Card color={colors.pink}>
            <Text style={styles.muted}>Objetivos em andamento</Text>
            <Text style={styles.h2}>
              {report?.goals.filter((g) => g.status !== "completed").length ||
                0}
            </Text>
            <Text style={styles.muted}>Seu futuro tomando forma.</Text>
          </Card>
        </View>
      </View>
      {report && <FinanceCharts report={report} categories={categories} />}
      <Text style={styles.h2}>Como estão seus limites?</Text>
      {report?.budgets.length ? (
        report.budgets.slice(0, 3).map((b) => (
          <Card key={b.id}>
            <View style={styles.row}>
              <Text style={[styles.body, { fontWeight: "700", flex: 1 }]}>
                {b.category === "total"
                  ? "Todos os gastos"
                  : categories.find((c) => c.id === b.category)?.label}
              </Text>
              <Text
                style={{
                  color: b.status === "exceeded" ? colors.danger : colors.green,
                }}
              >
                {b.status === "exceeded"
                  ? "Acima do limite"
                  : b.status === "attention"
                    ? "Atenção"
                    : "Dentro do limite"}
              </Text>
            </View>
            <Progress
              value={(b.spent_cents / b.limit_cents) * 100}
              label="Uso do orçamento"
            />
            <Text style={styles.muted}>
              {money(b.spent_cents)} de {money(b.limit_cents)} ·{" "}
              {b.month.slice(0, 7)}
            </Text>
          </Card>
        ))
      ) : (
        <Empty
          title="Um limite é um cuidado"
          detail="Defina seu primeiro orçamento para comparar seus gastos com o que você planejou."
        />
      )}
      <Button label="Cuidar dos meus planos" secondary onPress={onPlans} />
      <Card color="#EFE6F3">
        <Text style={styles.h2}>Sua semana, com perspectiva</Text>
        <Text style={styles.body}>
          Veja o que mudou, onde você está dentro do orçamento e como avançam
          suas metas.
        </Text>
        <Button label="Ver meu relatório" onPress={onReport} />
      </Card>
    </View>
  );
}
