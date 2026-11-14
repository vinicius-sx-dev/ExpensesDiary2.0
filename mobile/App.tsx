import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "./src/stores/auth";
import { useFinance } from "./src/stores/finance";
import { Auth } from "./src/screens/Auth";
import { Home } from "./src/screens/Home";
import { Ledger } from "./src/screens/Ledger";
import { Plans } from "./src/screens/Plans";
import { Reports } from "./src/screens/Reports";
import { EntryForm } from "./src/components/FinanceForms";
import { Button, ErrorBox, styles, colors } from "./src/components/ui";
import { api } from "./src/lib/api";
const tabs = [
  { id: "home", label: "Hoje", icon: "◉" },
  { id: "ledger", label: "Diário", icon: "≡" },
  { id: "plans", label: "Planos", icon: "✳" },
  { id: "reports", label: "Semana", icon: "▤" },
] as const;
type Tab = (typeof tabs)[number]["id"];
function Dashboard() {
  const [tab, setTab] = useState<Tab>("home"),
    [add, setAdd] = useState(false),
    [logoutError, setLogoutError] = useState<string | null>(null),
    [loggingOut, setLoggingOut] = useState(false);
  const { loading, error, load } = useFinance();
  const scroll = useRef<React.ElementRef<typeof ScrollView>>(null);
  const { width } = useWindowDimensions();
  useEffect(() => {
    void load();
  }, []);
  function navigate(t: Tab) {
    setTab(t);
    scroll.current?.scrollTo({ y: 0, animated: false });
  }
  const logout = async () => {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await api("/auth/logout", "POST");
      await useAuth.getState().clear();
    } catch (e) {
      setLogoutError(
        "Não foi possível revogar a sessão no servidor. Tente novamente com conexão ou saia deste aparelho. A sessão no servidor poderá continuar válida até expirar.",
      );
    } finally {
      setLoggingOut(false);
    }
  };
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
      <View
        style={{
          paddingHorizontal: 24,
          paddingVertical: 12,
          maxWidth: 1000,
          width: "100%",
          alignSelf: "center",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Text style={[styles.h2, { fontSize: width < 360 ? 17 : 21 }]}>
          ✳ ExpensesDiary
        </Text>
        <Pressable
          accessibilityRole="button"
          disabled={loggingOut}
          onPress={logout}
          style={{ padding: 12 }}
        >
          <Text style={styles.muted}>{loggingOut ? "Saindo…" : "Sair"}</Text>
        </Pressable>
      </View>
      <ScrollView
        ref={scroll}
        contentContainerStyle={{
          padding: 24,
          paddingTop: 12,
          paddingBottom: 32,
          gap: 18,
          maxWidth: 800,
          width: "100%",
          alignSelf: "center",
        }}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={load}
            tintColor={colors.green}
          />
        }
      >
        <ErrorBox message={error || logoutError} />
        {logoutError ? (
          <Button label="Sair somente deste aparelho" secondary onPress={async () => {
            try { await useAuth.getState().clear(); }
            catch { setLogoutError("Não foi possível remover a sessão do armazenamento do aparelho."); }
          }} />
        ) : null}
        {error ? (
          <Button label="Tentar atualizar" secondary onPress={load} />
        ) : null}
        {loading && !useFinance.getState().report ? (
          <ActivityIndicator color={colors.green} />
        ) : null}
        {tab === "home" ? (
          <Home
            onAdd={() => setAdd(true)}
            onPlans={() => navigate("plans")}
            onReport={() => navigate("reports")}
          />
        ) : tab === "ledger" ? (
          <>
            <View style={{ alignItems: "flex-end" }}>
              <Button label="＋ Lançamento" onPress={() => setAdd(true)} />
            </View>
            <Ledger />
          </>
        ) : tab === "plans" ? (
          <Plans />
        ) : (
          <Reports onOpenSaved={() => scroll.current?.scrollTo({ y: 0, animated: true })} />
        )}
      </ScrollView>
      <View
        style={{
          flexDirection: "row",
          paddingHorizontal: 10,
          paddingVertical: 10,
          borderTopWidth: 1,
          borderColor: colors.line,
          backgroundColor: colors.white,
        }}
      >
        {tabs.map((t) => (
          <Pressable
            key={t.id}
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === t.id }}
            onPress={() => navigate(t.id)}
            style={{
              flex: 1,
              minHeight: 56,
              borderRadius: 18,
              gap: 3,
              padding: 8,
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: tab === t.id ? colors.lime : "transparent",
            }}
          >
            <Text style={{ fontSize: 22, color: colors.ink }}>{t.icon}</Text>
            <Text
              style={{ fontSize: 12, fontWeight: "700", color: colors.ink }}
            >
              {t.label}
            </Text>
          </Pressable>
        ))}
      </View>
      {add ? <EntryForm onClose={() => setAdd(false)} /> : null}
    </SafeAreaView>
  );
}
export default function App() {
  const { ready, access, refresh, generation, hydrate } = useAuth();
  useEffect(() => {
    void hydrate();
  }, []);
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" />
      {!ready ? (
        <View
          style={{
            flex: 1,
            justifyContent: "center",
            backgroundColor: colors.paper,
          }}
        >
          <ActivityIndicator color={colors.green} />
        </View>
      ) : access || refresh ? (
        <Dashboard key={generation} />
      ) : (
        <Auth />
      )}
    </SafeAreaProvider>
  );
}
