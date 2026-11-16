import { test, expect } from "@playwright/test";
// UI-only fixtures. The API security/finance suite exercises the actual server separately.
const report = {
  week_start: "2026-11-09",
  week_end: "2026-11-12",
  partial: true,
  income_cents: 320000,
  expense_cents: 84550,
  net_cents: 235450,
  available_cents: 205450,
  reserved_cents: 30000,
  unreserved_flow_cents: 205450,
  required_weekly_cents: 15000,
  goal_gap_cents: 0,
  categories: [
    { category: "mercado", amount_cents: 42550 },
    { category: "restaurante", amount_cents: 42000 },
  ],
  budgets: [
    {
      id: 1,
      month: "2026-11-01",
      category: "mercado",
      limit_cents: 80000,
      spent_cents: 42550,
      remaining_cents: 37450,
      status: "within",
    },
  ],
  goals: [
    {
      id: 1,
      title: "Minha primeira reserva",
      motivation: "Mais tranquilidade",
      target_cents: 500000,
      deadline: "2027-06-01",
      saved_cents: 120000,
      remaining_cents: 380000,
      required_weekly_cents: 15000,
      status: "in_progress",
    },
  ],
  note: "Fluxo dos lançamentos informados. Não é saldo bancário.",
};
for (const width of [360, 768, 1280]) {
  test(`login and finance navigation at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("https://api.example.test/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const data: Record<string, unknown> = {
        "/auth/login": { challenge_id: "a".repeat(64), expires_in: 300 },
        "/auth/verify": {
          access_token: "ui-fixture-only",
          refresh_token: "ui-fixture-only",
        },
        "/advisor/preferences": { municipality: "4106902", notifications_enabled: false, selected_goal_id: 1, timezone: "America/Sao_Paulo", max_per_week: 2, quiet_start: 20, quiet_end: 9 },
        "/advisor/regions": { "4106902": "Curitiba", "4114501": "Manoel Ribas" },
        "/advisor/patterns": { goal: { actual_monthly_cents: 50000, planned_monthly_cents: 80000, gap_cents: 30000, assumptions: "Média dos aportes registrados nos três meses completos." }, patterns: [{ strategy: "fast_food", occurrences: 12, average_cents: 4000, weekday: 4, hour: 18, action: "Substituir uma refeição fora por uma receita caseira" }], note: "Histórico informado." },
        "/advisor/simulate": { result: { status: "prices_unavailable", message: "Preços locais indisponíveis: não há cotações verificáveis suficientes.", alternative: { name: "Sanduíche frio de queijo e tomate" } } },
        "/imports": [],
        "/imports/preview": { id: "preview-fixture", expires_at: 9999999999,
          income_cents: 10000, expense_cents: 2000, rows: [
            {index: 0, on_date: "2025-01-01", amount_cents: 10000, kind: "income", possible_duplicate: false},
            {index: 1, on_date: "2025-01-02", amount_cents: 2000, kind: "expense", possible_duplicate: true},
          ] },
        "/imports/preview-fixture/confirm": { imported_count: 1 },
        "/categories": [
          {
            id: "mercado",
            label: "Mercado",
            group: "Alimentação",
            kind: "expense",
          },
          {
            id: "restaurante",
            label: "Restaurante",
            group: "Alimentação",
            kind: "expense",
          },
          {
            id: "salario",
            label: "Salário",
            group: "Receitas",
            kind: "income",
          },
        ],
        "/movements": [
          {
            id: 1,
            request_id: "fixture",
            category: "mercado",
            kind: "expense",
            amount_cents: 42550,
            on_date: "2026-11-12",
            description: "Compras da semana",
            payment_method: "pix",
            essential: true,
          },
        ],
        "/goals": report.goals,
        "/budgets": report.budgets,
        "/reports/weekly": report,
        "/reports/history": [report],
        "/reports/weekly/insights": {summary: "Resumo gerado pela IA.", suggestions: ["Acompanhe seu orçamento."]},
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify(data[path] || {}),
      });
    });
    await page.goto("/");
    await page
      .getByLabel("E-mail", { exact: true })
      .fill("preview@example.com");
    await page.getByLabel("Senha", { exact: true }).fill("preview-password");
    await page.screenshot({
      path: testInfo.outputPath("login.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Continuar", exact: true }).click();
    await page.getByLabel("Código de 6 dígitos").fill("123456");
    await page.getByRole("button", { name: "Confirmar e entrar" }).click();
    await expect(
      page.getByText("Pequenos cuidados.", { exact: false }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("home.png"),
      fullPage: true,
    });
    for (const name of ["Diário", "Planos", "Semana"]) {
      await page.getByRole("tab", { name: new RegExp(name) }).click();
      await expect(
        page.getByText(
          name === "Diário"
            ? "Seu dia a dia"
            : name === "Planos"
              ? "Planos que crescem"
              : "Uma pausa para olhar",
          { exact: true },
        ),
      ).toBeVisible();
      if (name === "Diário") {
        await expect(page.getByRole("button", { name: "Selecionar extrato" })).toBeDisabled();
        await expect(page.getByRole("radio")).toHaveCount(10);
        await page.getByRole("radio", { name: "Nubank", exact: true }).click();
        const uploadRequest = page.waitForRequest(r => new URL(r.url()).pathname === "/imports/preview");
        const fileChooser = page.waitForEvent("filechooser");
        await page.getByRole("button", { name: "Selecionar extrato" }).click();
        await (await fileChooser).setFiles("tests/fixtures/statement.csv");
        const uploaded = await uploadRequest;
        expect(uploaded.headers()["content-type"]).toMatch(/^multipart\/form-data; boundary=/);
        expect(uploaded.headers().authorization).toBe("Bearer ui-fixture-only");
        expect(uploaded.postData()).toContain('name="institution"\r\n\r\nNUBANK');
        expect(uploaded.postData()).toContain('name="file"; filename="statement.csv"');
        await expect(page.getByText("Conferir 2 movimentações")).toBeVisible();
        await expect(page.getByRole("checkbox").nth(0)).toBeChecked();
        await expect(page.getByRole("checkbox").nth(1)).not.toBeChecked();
        await page.getByRole("checkbox").nth(1).click();
        await expect(page.getByRole("button", { name: "Confirmar 2 movimentações" })).toBeVisible();
        await page.getByRole("checkbox").nth(1).click();
        await page.screenshot({ path: testInfo.outputPath("statement-preview.png"), fullPage: true });
        await page.getByRole("button", {name: "Revisar categoria", exact: true}).first().click();
        await page.getByRole("button", {name: "Salário", exact: true}).click();
        await page.getByRole("button", {name: "Confirmar categoria deste item", exact: true}).click();
        const confirmRequest = page.waitForRequest(r => r.url().endsWith("/imports/preview-fixture/confirm"));
        await page.getByRole("button", { name: "Confirmar 1 movimentações" }).click();
        expect((await confirmRequest).postDataJSON()).toEqual({ selected: [0], classifications: [{index: 0, category: "salario", essential: false, niche: null, unplanned: false}] });
        await expect(page.getByText(/1 movimentações importadas\. Entradas:/)).toBeVisible();
      }
      await page.screenshot({
        path: testInfo.outputPath(
          `${name === "Diário" ? "ledger" : name === "Planos" ? "plans" : "weekly"}.png`,
        ),
        fullPage: true,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
      ).toBe(false);
    }
    await page.getByRole("button", { name: "Enviar totais e pedir comentários à IA" }).click();
    await expect(page.getByText("Resumo gerado pela IA.")).toBeVisible();
    await expect(page.getByText("Receitas e despesas", {exact: true})).toBeVisible();
    await expect(page.getByText("Distribuição dos gastos", {exact: true})).toBeVisible();
    await expect(page.getByText("Proporção das movimentações", {exact: true})).toBeVisible();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar PDF do relatório exibido" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("expenses-diary-2026-11-09.pdf");
    await download.saveAs(testInfo.outputPath("weekly.pdf"));
    const stream = await download.createReadStream();
    let size = 0;
    for await (const chunk of stream!) {
      if (!size) expect(chunk.subarray(0, 5).toString()).toBe("%PDF-");
      size += chunk.length;
    }
    expect(size).toBeGreaterThan(1000);
    const saveDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Salvar retrato e exportar PDF" }).click();
    await saveDownload;
    await page.getByRole("button", { name: "Ver últimos retratos salvos" }).click();
    const openDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Abrir 2026-11-09" }).click();
    await openDownload;
    await expect(page.getByText("Exibindo retrato salvo", {exact: false})).toBeVisible();
    await page.getByRole("tab", {name: /Dicas/}).click();
    await expect(page.getByText("Alternativas para sua meta", {exact:true})).toBeVisible();
    await page.getByRole("button", {name:"Analisar meu histórico"}).click();
    await page.getByRole("button", {name:"Alimentação fora",exact:true}).click();
    await page.getByRole("button", {name:"Calcular alternativa"}).click();
    await expect(page.getByText("Preços locais indisponíveis:", {exact:false})).toBeVisible();
    await expect(page.getByText("Conclusão projetada:", {exact:false})).not.toBeVisible();
    await page.screenshot({path:testInfo.outputPath("advisor.png"),fullPage:true});
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    expect(errors).toEqual([]);
  });
}
