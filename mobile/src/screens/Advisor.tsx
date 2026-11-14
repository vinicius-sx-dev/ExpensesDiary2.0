import React, { useEffect, useState } from 'react';
import { Linking, Switch, Text, View } from 'react-native';
import { api } from '../lib/api';
import { cents, money } from '../lib/types';
import { registerPush } from '../lib/notifications';
import { useFinance } from '../stores/finance';
import { Button, Choices, ErrorBox, Field, styles } from '../components/ui';

type Preferences = { municipality: string | null; notifications_enabled: boolean; selected_goal_id: number | null; timezone: string; max_per_week: number; quiet_start: number; quiet_end: number };
type Pattern = { strategy: string; occurrences: number; average_cents: number; weekday: number | null; hour: number | null; action: string };
type Analysis = { goal: { actual_monthly_cents: number; planned_monthly_cents: number; gap_cents: number; assumptions: string }; patterns: Pattern[]; note: string };
type Result = { status: string; message?: string; monthly_savings_cents?: number; per_occurrence_cents?: number; completion_date?: string | null; days_earlier?: number | null; note?: string; alternative?: { name: string; portion_cents?: number; consumed_cents?: number; packages_cents?: number; steps?: string; allergens?: string; note?: string; ingredients?: { name: string; quantity: string; unit: string; consumed_cents: number; sources: { product: string; package_price_cents: number; package_quantity: string; unit: string; source_url: string; observed_at: string }[] }[] } };
const labels: Record<string,string> = { fast_food: 'Alimentação fora', subscriptions: 'Assinaturas', impulse: 'Compras não planejadas', beauty: 'Estética', tattoo: 'Tatuagem', travel: 'Viagens não planejadas' };

export function Advisor() {
  const goals = useFinance(s => s.goals);
  const [pref, setPref] = useState<Preferences | null>(null);
  const [regions, setRegions] = useState<Record<string,string>>({});
  const [search, setSearch] = useState('');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [strategy, setStrategy] = useState('');
  const [recipe, setRecipe] = useState('sandwich');
  const [frequency, setFrequency] = useState('1');
  const [cost, setCost] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [useAI, setUseAI] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    Promise.all([api<Preferences>('/advisor/preferences'), api<Record<string,string>>('/advisor/regions')])
      .then(([p,r]) => { if (live) { setPref(p); setRegions(r); } })
      .catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, []);
  async function run(fn: () => Promise<void>) {
    setError(null); setBusy(true);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível concluir.'); }
    finally { setBusy(false); }
  }
  async function saveNotifications(enabled: boolean) {
    if (!pref) return;
    const next = { ...pref, notifications_enabled: enabled };
    await api('/advisor/preferences', 'PUT', next);
    setPref(next);
    if (enabled) {
      try { await registerPush(); }
      catch (e) {
        const rollback = { ...next, notifications_enabled: false };
        await api('/advisor/preferences', 'PUT', rollback); setPref(rollback); throw e;
      }
    } else await api('/advisor/devices', 'DELETE');
  }
  return <View style={{ gap: 16 }}>
    <Text style={styles.h2}>Alternativas para sua meta</Text>
    <Text style={styles.body}>Escolha uma meta e sua cidade no Paraná. Os cálculos usam apenas o histórico informado. Se faltarem preços locais verificáveis, vamos avisar.</Text>
    <ErrorBox message={error} />
    {pref && <>
      <Choices items={goals.map(g => ({ id: String(g.id), label: g.title }))} value={String(pref.selected_goal_id || '')} onChange={id => { if (busy) return; setPref({ ...pref, selected_goal_id: Number(id) }); setAnalysis(null); setResult(null); }} />
      {!goals.length && <Text style={styles.muted}>Crie um objetivo em Planos para começar.</Text>}
      <Text style={styles.body}>Cidade: {pref.municipality ? regions[pref.municipality] : 'não selecionada'}</Text>
      <Field label="Buscar cidade do Paraná" value={search} onChangeText={setSearch} />
      {search.length > 1 && <Choices items={Object.entries(regions).filter(([,name]) => name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(search.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase())).slice(0,12).map(([id,label]) => ({id,label}))} value={pref.municipality || ''} onChange={id => { if (busy) return; setPref({ ...pref, municipality: id }); setSearch(''); setResult(null); }} />}
      <Button label="Analisar meu histórico" busy={busy} onPress={() => run(async () => {
        if (!pref.selected_goal_id) throw new Error('Selecione uma meta.');
        await api('/advisor/preferences','PUT',pref);
        setAnalysis(await api<Analysis>('/advisor/patterns?goal_id=' + pref.selected_goal_id)); setResult(null); setStrategy('');
      })} />
      <Text style={styles.muted}>Lembretes: até dois por semana, entre 9h e 20h. O horário depende de padrões com evidência suficiente. Abra uma simulação para escolher uma alternativa antes dos lembretes.</Text>
      <Button secondary busy={busy} label={pref.notifications_enabled ? 'Desativar lembretes' : 'Ativar push neste aparelho'} onPress={() => run(() => saveNotifications(!pref.notifications_enabled))} />
    </>}
    {analysis && <>
      <Text style={styles.body}>Planejado: {money(analysis.goal.planned_monthly_cents)}/mês · Registrado: {money(analysis.goal.actual_monthly_cents)}/mês · Diferença: {money(analysis.goal.gap_cents)}</Text>
      <Text style={styles.muted}>{analysis.goal.assumptions}</Text>
      {!analysis.patterns.length && <Text style={styles.body}>Ainda não há recorrência suficiente para sugerir uma mudança.</Text>}
      <Choices items={analysis.patterns.map(p => ({id:p.strategy,label:labels[p.strategy] || p.strategy}))} value={strategy} onChange={id => {if (busy) return;setStrategy(id);setResult(null);}} />
      {strategy && <>
        <Text style={styles.body}>{analysis.patterns.find(p => p.strategy === strategy)?.action}</Text>
        {strategy === 'fast_food' ? <Choices items={[{id:'sandwich',label:'Sanduíche frio'},{id:'oats',label:'Aveia, leite e banana'}]} value={recipe} onChange={setRecipe} /> : <Field label="Custo da alternativa/multa por ocorrência (R$; 0 se não houver)" value={cost} onChangeText={setCost} keyboardType="decimal-pad" />}
        <Field label="Ocorrências a substituir por mês" value={frequency} onChangeText={setFrequency} keyboardType="number-pad" />
        <View style={styles.row}><Text style={[styles.muted,{flex:1}]}>Pedir uma mensagem à IA usando somente categoria e resultados calculados</Text><Switch value={useAI} onValueChange={setUseAI} accessibilityLabel="Permitir mensagem da IA" /></View>
        <Button busy={busy} label="Calcular alternativa" onPress={() => run(async () => {
          if (!/^\d+$/.test(frequency)) throw new Error('Informe uma quantidade inteira.');
          const response = await api<{result:Result;message?:string}>('/advisor/simulate','POST',{goal_id:pref?.selected_goal_id,strategy,recipe_id:recipe,occurrences_per_month:Number(frequency),replacement_cents:strategy === 'fast_food' ? null : cost.trim() === '0' ? 0 : cents(cost),humanize:useAI});
          setResult(response.result); setMessage(response.message || '');
        })} />
      </>}
    </>}
    {result && <View style={{gap:12}}>
      <Text style={styles.h2}>{result.alternative?.name || 'Resultado da simulação'}</Text>
      {result.message && <Text style={styles.body}>{result.message}</Text>}
      {result.status === 'ready' && <>
        {!!message && <Text style={styles.body}>{message}</Text>}
        <Text style={styles.body}>Economia: {money(result.per_occurrence_cents || 0)} por ocorrência · {money(result.monthly_savings_cents || 0)}/mês</Text>
        <Text style={styles.body}>Conclusão projetada: {result.completion_date || 'sem previsão'}. {result.days_earlier == null ? 'Sem ritmo anterior suficiente para calcular antecipação.' : `${result.days_earlier} dias antes, sob as premissas da simulação.`}</Text>
        {result.alternative?.portion_cents != null && <Text style={styles.body}>Porção: {money(result.alternative.portion_cents)} · Receita: {money(result.alternative.consumed_cents || 0)} · Compra média das embalagens: {money(result.alternative.packages_cents || 0)}</Text>}
        {result.alternative?.ingredients?.map(i => <View key={i.name} style={{gap:6}}>
          <Text style={styles.body}>{i.name}: {i.quantity} {i.unit} · {money(i.consumed_cents)}</Text>
          {i.sources.map((s,index) => <Text key={index} accessibilityRole="link" style={styles.muted} onPress={() => { if (s.source_url.startsWith('https://')) void Linking.openURL(s.source_url); }}>{s.product} · {s.package_quantity} {s.unit} · {money(s.package_price_cents)} · ver fonte ({s.observed_at.slice(0,10)})</Text>)}
        </View>)}
        <Text style={styles.body}>{result.alternative?.steps}</Text>
        <Text style={styles.muted}>{result.alternative?.allergens}</Text>
        <Text style={styles.muted}>{result.alternative?.note}</Text>
        <Text style={styles.muted}>{result.note}</Text>
      </>}
    </View>}
  </View>;
}
