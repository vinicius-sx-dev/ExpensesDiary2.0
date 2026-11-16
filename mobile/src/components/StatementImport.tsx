import React, { useEffect, useState } from "react";
import { Platform, Pressable, Switch, Text, View } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import { api } from "../lib/api";
import { money } from "../lib/types";
import { useFinance } from "../stores/finance";
import { CategoryPicker } from "./FinanceForms";
import { Button, Card, Choices, colors, styles } from "./ui";

type Row = { index: number; on_date: string; amount_cents: number; kind: "income" | "expense"; possible_duplicate: boolean; review_reason?: string; category?: string; classification_source?: string; context?: { merchant?: string } };
type Classification = { index: number; category: string; essential: boolean; niche: string | null; unplanned: boolean };
type Preview = { id: string; expires_at: number; rows: Row[]; income_cents: number; expense_cents: number };

const INSTITUTIONS = [
  ["PICPAY", "PicPay"], ["NUBANK", "Nubank"], ["BANCO_DO_BRASIL", "Banco do Brasil"],
  ["ITAU", "Itaú"], ["BRADESCO", "Bradesco"], ["SANTANDER", "Santander"],
  ["CAIXA", "Caixa Econômica Federal"], ["BTG", "BTG Pactual"],
  ["SICREDI", "Sicredi"], ["MERCADO_PAGO", "Mercado Pago"],
] as const;

export function StatementImport() {
  const categories = useFinance(s => s.categories);
  const [classifications, setClassifications] = useState<Record<number, Classification>>({});
  const [editing, setEditing] = useState<number | null>(null);
  const [allowDuplicates, setAllowDuplicates] = useState(false);
  const choice = (r: Row): Classification => classifications[r.index] || {
    index: r.index, category: r.category || (r.kind === "expense" ? "outros" : "outras_receitas"),
    essential: false, niche: null, unplanned: false,
  };
  const classify = (r: Row, patch: Partial<Classification>) => setClassifications(old => ({
    ...old, [r.index]: { ...choice(r), ...patch },
  }));
  const [institution, setInstitution] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState<{ id: string; expires_at: number }[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [page, setPage] = useState(0);
  const refresh = async () => setPending(await api("/imports"));
  useEffect(() => { refresh().catch(() => {}); }, []);
  const show = (p: Preview) => {
    setPreview(p); setPage(0); setClassifications({}); setEditing(null); setAllowDuplicates(false);
    setSelected(new Set(p.rows.filter(r => !r.possible_duplicate && !r.review_reason).map(r => r.index)));
  };
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setMessage("");
    try { await action(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Não foi possível importar."); }
    finally { setBusy(false); }
  };
  const choose = () => run(async () => {
    if (!institution) throw new Error("Selecione a instituição financeira.");
    const result = await DocumentPicker.getDocumentAsync({ type: "*/*", multiple: false, copyToCacheDirectory: true });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (!asset) return;
    const format = asset.name.split(".").pop()?.toLowerCase();
    const local = Platform.OS === "web" ? null : new File(asset.uri);
    try {
      if (!format || !["csv", "ofx", "xml", "pdf", "docx"].includes(format))
        throw new Error("Escolha CSV, OFX, XML, PDF textual ou DOCX. DOC antigo e arquivos com macros não são aceitos.");
      const size = asset.size ?? local?.size ?? asset.file?.size;
      if (size == null || size > 5 * 1024 * 1024 || size === 0)
        throw new Error("O arquivo precisa ter até 5 MiB. Divida o histórico por período.");
      if (local) {
        // Raw bytes avoid incompatible native FormData implementations; backend applies the same limits.
        show(await api<Preview>("/imports/preview?format=" + format + "&institution=" + institution, "POST", await local.bytes()));
        await refresh();
        return;
      }
      const body = new FormData();
      body.append("institution", institution);
      if (Platform.OS === "web") {
        if (!asset.file) throw new Error("Não foi possível ler o arquivo selecionado.");
        body.append("file", asset.file, asset.name);
      } else {
        body.append("file", { uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" } as unknown as Blob);
      }
      show(await api<Preview>("/imports/preview", "POST", body));
      await refresh();
    } finally {
      // Only delete the picker-created cache copy, never the user's original.
      if (local?.exists) local.delete();
    }
  });
  const selectedRows = preview?.rows.filter(r => selected.has(r.index)) ?? [];
  const income = selectedRows.filter(r => r.kind === "income").reduce((n, r) => n + r.amount_cents, 0);
  const expense = selectedRows.filter(r => r.kind === "expense").reduce((n, r) => n + r.amount_cents, 0);
  return <Card>
    <Text style={styles.h2}>Importar extrato</Text>
    <Text style={styles.body}>CSV, OFX, XML, PDF textual ou Word (.docx). Confira as movimentações antes de salvar. Data, valor, entrada/saída e, quando identificáveis, horário e estabelecimento serão registrados.</Text>
    <Text style={styles.muted}>Até 5 MiB e 2.000 movimentações por arquivo; 6 envios/minuto e 120/dia. Para vários anos, envie por períodos. Layouts não reconhecidos serão recusados; prefira CSV/OFX.</Text>
    {!preview && <>
      <Text style={styles.h2}>Instituição financeira (obrigatório)</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {INSTITUTIONS.map(([id, label]) => <Pressable key={id} accessibilityRole="radio"
          accessibilityLabel={label} accessibilityState={{ checked: institution === id, disabled: busy }}
          disabled={busy} onPress={() => setInstitution(id)}
          style={{ padding: 12, borderWidth: 2, borderRadius: 8, borderColor: institution === id ? colors.green : colors.line }}>
          <Text style={styles.body}>{institution === id ? "● " : "○ "}{label}</Text>
        </Pressable>
      )}
      </View>
      <Button label="Selecionar extrato" disabled={!institution} busy={busy} onPress={choose} />
    </>}
    {busy && <Text accessibilityRole="alert" style={styles.body}>Processando solicitação. Aguarde…</Text>}
    {!preview && pending.map(p => <Button key={p.id} label="Retomar prévia pendente" secondary busy={busy} onPress={() => run(async () => show(await api<Preview>(`/imports/${p.id}`)))} />)}
    {preview && <>
      <Text style={styles.h2}>Conferir {preview.rows.length} movimentações</Text>
      <Text style={styles.body}>Selecionadas: {selected.size} · Entradas: {money(income)} · Saídas: {money(expense)}</Text>
      <Text style={styles.muted}>Possíveis duplicatas começam desmarcadas. Confira transferências entre suas próprias contas, valores já lançados e o período. Saldos anteriores não são importados. A prévia expira em uma hora.</Text>
      <Text style={styles.muted}>Revise as categorias sugeridas. Use “Revisar categoria” para confirmar categoria, contexto e essencialidade. Somente escolhas revisadas ensinam o classificador e alimentam as dicas; itens sem revisão continuam nos totais.</Text>
      <Button label="Atualizar prévia" secondary busy={busy} onPress={() => run(async () => show(await api<Preview>(`/imports/${preview.id}`)))} />
      <Button label="Desmarcar todas" secondary disabled={busy} onPress={() => setSelected(new Set())} />
      <Button label="Selecionar sem duplicatas ou movimentações internas" secondary disabled={busy} onPress={() => setSelected(new Set(preview.rows.filter(r => !r.possible_duplicate && !r.review_reason).map(r => r.index)))} />
      {preview.rows.slice(page * 25, page * 25 + 25).map(r => <View key={r.index} style={{ gap: 8 }}><Pressable disabled={busy} accessibilityRole="checkbox" aria-checked={selected.has(r.index)} aria-disabled={busy} accessibilityState={{ checked: selected.has(r.index), disabled: busy }} onPress={() => setSelected(old => { const next = new Set(old); next.has(r.index) ? next.delete(r.index) : next.add(r.index); return next; })} style={{ padding: 12, borderWidth: 1, borderRadius: 8, borderColor: selected.has(r.index) ? colors.green : colors.line }}>
        <Text style={styles.body}>{selected.has(r.index) ? "✓ " : "○ "}{r.on_date.split("-").reverse().join("/")} · {r.kind === "income" ? "Entrada" : "Saída"} · {money(r.amount_cents)}</Text>
        {!!r.context?.merchant && <Text style={styles.muted}>{r.context.merchant}</Text>}
        {r.review_reason === "internal_transfer" && <Text style={{color: colors.danger}}>Dinheiro guardado/resgatado: movimentação interna, não consumo ou renda nova. Deixe desmarcado para não distorcer os totais. Se selecionar, será registrado como entrada/saída comum.</Text>}
        {r.possible_duplicate && <Text style={{ color: colors.danger }}>Possível duplicata: confira antes de selecionar.</Text>}
      </Pressable>
        <Text style={styles.body}>Categoria: {categories.find(c => c.id === choice(r).category)?.label || choice(r).category}
          {classifications[r.index] ? " · Revisada" : r.classification_source === "history" ? " · Sugerida pelo seu histórico" : " · A revisar"}
        </Text>
        <Button label={editing === r.index ? "Fechar categoria" : "Revisar categoria"} secondary disabled={busy} onPress={() => setEditing(editing === r.index ? null : r.index)} />
        {editing === r.index && <View style={{ gap: 10, opacity: busy ? 0.6 : 1 }} pointerEvents={busy ? "none" : "auto"}>
          <CategoryPicker value={choice(r).category} kind={r.kind} onChange={category => classify(r, {category})} />
          {r.kind === "expense" && <>
            <Text style={styles.body}>Essencial para mim</Text>
            <Switch accessibilityLabel="Despesa importada essencial" value={choice(r).essential} onValueChange={essential => classify(r, {essential})} disabled={busy} />
            <Choices items={[{id:"",label:"Sem contexto"},{id:"fast_food",label:"Lanches / fast-food"},{id:"subscriptions",label:"Assinaturas"},{id:"impulse",label:"Compra por impulso"},{id:"beauty",label:"Estética"},{id:"tattoo",label:"Tatuagem"},{id:"travel",label:"Viagem"}]}
              value={choice(r).niche || ""} onChange={niche => classify(r, {niche: niche || null})} />
            <Text style={styles.body}>Gasto não planejado por mim</Text>
            <Switch accessibilityLabel="Despesa importada não planejada" value={choice(r).unplanned} onValueChange={unplanned => classify(r, {unplanned})} disabled={busy} />
          </>}
          <Button label="Confirmar categoria deste item" disabled={busy} onPress={() => { classify(r, {}); setEditing(null); }} />
        </View>}
      </View>)}
      <View style={styles.row}>
        <Button label="Anterior" secondary disabled={busy || page === 0} onPress={() => setPage(page - 1)} />
        <Text style={styles.muted}>{page + 1}/{Math.ceil(preview.rows.length / 25)}</Text>
        <Button label="Próxima" secondary disabled={busy || (page + 1) * 25 >= preview.rows.length} onPress={() => setPage(page + 1)} />
      </View>
      {selectedRows.some(r => r.possible_duplicate) && <View style={{gap: 8}}>
        <Text style={styles.body}>Revisei as possíveis duplicatas selecionadas e quero importá-las.</Text>
        <Switch accessibilityLabel="Autorizar possíveis duplicatas" value={allowDuplicates} onValueChange={setAllowDuplicates} disabled={busy} />
      </View>}
      <Button label={`Confirmar ${selected.size} movimentações`} busy={busy} disabled={!selected.size || (selectedRows.some(r => r.possible_duplicate) && !allowDuplicates)} onPress={() => run(async () => {
        const result = await api<{ imported_count: number }>(`/imports/${preview.id}/confirm`, "POST", { selected: [...selected],
          ...(Object.values(classifications).some(c => selected.has(c.index)) ? {classifications: Object.values(classifications).filter(c => selected.has(c.index))} : {}),
          ...(allowDuplicates ? {allow_duplicates: true} : {}),
        });
        setPreview(null); setSelected(new Set());
        setMessage(`${result.imported_count} movimentações importadas. Entradas: ${money(income)} · Saídas: ${money(expense)}.`);
        await useFinance.getState().load(); await refresh();
      })} />
      <Button label="Descartar prévia" secondary disabled={busy} onPress={() => run(async () => {
        await api(`/imports/${preview.id}`, "DELETE"); setPreview(null); await refresh();
      })} />
    </>}
    {!!message && <Text accessibilityRole="alert" style={styles.body}>{message}</Text>}
  </Card>;
}
