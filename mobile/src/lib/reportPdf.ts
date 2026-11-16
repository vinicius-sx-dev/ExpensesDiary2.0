import { Platform } from "react-native";
import type { Category, Report, Insight } from "./types";
import { money } from "./types";

const dateLabel = (value: string) => value.split("-").reverse().join("/");
const pdfMoney = (value: number) => money(value).replace(/\s/g, " ");
const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export async function exportReportPdf(report: Report, categories: Category[], insight?: Insight | null) {
  const categoryName = (id: string) =>
    id === "total" ? "Todos os gastos" : categories.find((item) => item.id === id)?.label || id;
  const sections = [
    {
      title: "Resumo",
      lines: [
        ...(report.available_cents !== undefined ? [`Saldo disponível acumulado: ${pdfMoney(report.available_cents)}`] : []),
        `Receitas: ${pdfMoney(report.income_cents)}`,
        `Despesas: ${pdfMoney(report.expense_cents)}`,
        `Fluxo líquido: ${pdfMoney(report.net_cents)}`,
        `Aportes na semana: ${pdfMoney(report.reserved_cents)}`,
        `Fluxo após aportes na semana: ${pdfMoney(report.unreserved_flow_cents)}`,
      ],
    },
    {
      title: "Despesas por categoria",
      lines: report.categories.map((item) =>
        `${categoryName(item.category)}: ${pdfMoney(item.amount_cents)}` +
        (item.essential_cents ? ` · Essenciais: ${pdfMoney(item.essential_cents)}` : ""),
      ),
    },
    {
      title: "Receitas por categoria",
      lines: (report.income_categories || []).map(item => `${categoryName(item.category)}: ${pdfMoney(item.amount_cents)}`),
    },
    {
      title: "Evolução diária",
      lines: (report.daily || []).map(day => `${dateLabel(day.date)} · Receitas: ${pdfMoney(day.income_cents)} · Despesas: ${pdfMoney(day.expense_cents)}`),
    },
    {
      title: "Orçamentos",
      lines: report.budgets.map((item) =>
        `${categoryName(item.category)} · ${item.month.slice(0, 7)}: ${pdfMoney(item.spent_cents)} de ${pdfMoney(item.limit_cents)}`,
      ),
    },
    {
      title: "Objetivos",
      lines: [
        `Reserva semanal estimada: ${pdfMoney(report.required_weekly_cents)}`,
        ...report.goals.map((goal) =>
          `${goal.title}: ${pdfMoney(goal.saved_cents)} de ${pdfMoney(goal.target_cents)} · Prazo: ${dateLabel(goal.deadline)}`,
        ),
      ],
    },
    ...(insight ? [{ title: "Comentários da IA", lines: [insight.summary, ...insight.suggestions] }] : []),
    { title: "Sobre os valores", lines: [report.note] },
  ];
  const period = `${dateLabel(report.week_start)} a ${dateLabel(report.week_end)}`;
  const status = report.partial ? "Semana em andamento" : "Semana encerrada";
  const filename = `expenses-diary-${report.week_start}.pdf`;

  if (Platform.OS === "web") {
    const { jsPDF } = await import("jspdf");
    const pdf = new jsPDF();
    let y = 20;
    function write(text: string, size: number) {
      pdf.setFontSize(size);
      const lines: string[] = pdf.splitTextToSize(text, 170);
      for (const line of lines) {
        if (y > 275) {
          pdf.addPage();
          y = 20;
        }
        pdf.text(line, 20, y);
        y += size / 2;
      }
    }
    write("ExpensesDiary | Relatório semanal", 18);
    write(period + " · " + status, 11);
    const maximum = Math.max(report.income_cents, report.expense_cents, 1);
    for (const [label, amount, color] of [
      ["Receitas", report.income_cents, "#226448"],
      ["Despesas", report.expense_cents, "#A32942"],
    ] as const) {
      write(label + ": " + pdfMoney(amount), 11);
      pdf.setFillColor(color);
      pdf.rect(20, y, 170 * amount / maximum, 5, "F");
      y += 10;
    }
    write(report.income_cents ? `Despesas / receitas: ${(report.expense_cents / report.income_cents * 100).toFixed(1)}%` : "Despesas / receitas: indisponível (sem receitas registradas).", 11);
    for (const section of sections) {
      y += 4;
      write(section.title, 14);
      for (const line of section.lines.length ? section.lines : ["Sem registros."]) {
        write(line, 11);
      }
    }
    pdf.save(filename);
    return;
  }

  const [print, sharing, fs] = await Promise.all([
    import("expo-print"), import("expo-sharing"), import("expo-file-system/legacy"),
  ]);
  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8">
    <style>body{font:14px Arial,sans-serif;color:#203a32;padding:24px}
    h1{font-size:26px}h2{font-size:18px;break-after:avoid}
    p{overflow-wrap:anywhere;line-height:1.5}</style></head>
    <body><h1>ExpensesDiary | Relatório semanal</h1><p>${period} · ${status}</p>
    <h2>Receitas e despesas</h2>
    ${([["Receitas", report.income_cents, "#226448"], ["Despesas", report.expense_cents, "#A32942"]] as const).map(([label, amount, color]) =>
      `<p>${label}: ${pdfMoney(amount)}</p><div style="height:14px;background:${color};width:${100 * amount / Math.max(1, report.income_cents, report.expense_cents)}%"></div>`).join("")}
    ${sections.map(({ title, lines }) =>
      `<h2>${title}</h2>${(lines.length ? lines : ["Sem registros."]).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}`,
    ).join("")}</body></html>`;
  const { uri } = await print.printToFileAsync({ html });
  try {
  // Android: o usuário escolhe a pasta; o arquivo deixa de depender do cache.
  if (Platform.OS === "android") {
    const permission = await fs.StorageAccessFramework.requestDirectoryPermissionsAsync();
    if (permission.granted) {
      const destination = await fs.StorageAccessFramework.createFileAsync(
        permission.directoryUri, filename, "application/pdf",
      );
      const base64 = await fs.readAsStringAsync(uri, { encoding: fs.EncodingType.Base64 });
      await fs.writeAsStringAsync(destination, base64, { encoding: fs.EncodingType.Base64 });
      return;
    }
  }
  if (!(await sharing.isAvailableAsync())) {
    throw new Error("PDF gerado, mas não salvo. Autorize uma pasta ou habilite o compartilhamento.");
  }
  await sharing.shareAsync(uri, {
    mimeType: "application/pdf",
    UTI: "com.adobe.pdf",
    dialogTitle: "Salvar relatório semanal",
  });
  } finally {
    await fs.deleteAsync(uri, { idempotent: true }).catch(() => {});
  }
}
