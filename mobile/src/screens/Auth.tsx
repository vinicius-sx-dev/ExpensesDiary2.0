import React, { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  Button,
  Field,
  ErrorBox,
  styles,
  colors,
  Card,
} from "../components/ui";
import { Garden } from "../components/Garden";
import { publicApi } from "../lib/api";
import { useAuth } from "../stores/auth";
export function Auth() {
  const [register, setRegister] = useState(false),
    [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [code, setCode] = useState(""),
    [challenge, setChallenge] = useState<string | null>(null),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      if (challenge) {
        const pair = await publicApi<{
          access_token: string;
          refresh_token: string;
        }>("/auth/verify", { challenge_id: challenge, code });
        await useAuth
          .getState()
          .setTokens(pair.access_token, pair.refresh_token);
      } else if (register) {
        if (password.length < 12)
          throw new Error("Use pelo menos 12 caracteres na senha.");
        await publicApi("/auth/register", {
          name: name.trim(),
          email: email.trim(),
          password,
        });
        setRegister(false);
        setMessage(
          "Cadastro solicitado. Entre para receber seu código por e-mail.",
        );
        setPassword("");
      } else {
        const result = await publicApi<{ challenge_id: string }>(
          "/auth/login",
          { email: email.trim(), password },
        );
        setChallenge(result.challenge_id);
        setPassword("");
        setMessage(
          "Enviamos um código para seu e-mail. Ele vale por 5 minutos.",
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            padding: 24,
            paddingBottom: 48,
            gap: 22,
            maxWidth: 520,
            width: "100%",
            alignSelf: "center",
          }}
        >
          <Text style={[styles.h2, { marginTop: 20 }]}>✳ ExpensesDiary</Text>
          <Garden />
          <Text style={styles.title}>
            Cuide do hoje.{"\n"}Cultive seus planos.
          </Text>
          <Text style={styles.muted}>
            Seu dinheiro, com mais clareza e espaço para o que importa.
          </Text>
          <Card>
            <Text style={styles.h2}>
              {challenge
                ? "Confira seu e-mail"
                : register
                  ? "Crie sua conta"
                  : "Que bom te ver por aqui"}
            </Text>
            {message ? <Text style={styles.body}>{message}</Text> : null}
            <ErrorBox message={error} />
            {challenge ? (
              <Field
                label="Código de 6 dígitos"
                value={code}
                onChangeText={setCode}
                keyboardType="number-pad"
                maxLength={6}
                textContentType="oneTimeCode"
                autoComplete="one-time-code"
              />
            ) : (
              <>
                {register ? (
                  <Field
                    label="Seu nome"
                    value={name}
                    onChangeText={setName}
                    maxLength={120}
                    autoComplete="name"
                  />
                ) : null}
                <Field
                  label="E-mail"
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  autoComplete="email"
                  maxLength={320}
                />
                <Field
                  label={register ? "Senha · mínimo 12 caracteres" : "Senha"}
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  maxLength={128}
                  autoComplete={register ? "new-password" : "current-password"}
                />
              </>
            )}
            <Button
              label={
                challenge
                  ? "Confirmar e entrar"
                  : register
                    ? "Criar conta"
                    : "Continuar"
              }
              busy={busy}
              onPress={submit}
            />
            <Button
              label={
                challenge
                  ? "Voltar e solicitar outro código"
                  : register
                    ? "Já tenho conta"
                    : "Quero criar uma conta"
              }
              secondary
              disabled={busy}
              onPress={() => {
                setChallenge(null);
                setCode("");
                setPassword("");
                setError(null);
                setMessage("");
                if (!challenge) setRegister(!register);
              }}
            />
          </Card>
          <Text style={styles.muted}>
            O acesso usa senha e um código enviado ao seu e-mail. Nunca
            compartilhe esse código.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
