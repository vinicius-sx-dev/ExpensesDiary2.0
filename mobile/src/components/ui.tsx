import React, { ReactNode } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  KeyboardAvoidingView,
  Platform,
  useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
export const colors = {
  ink: "#203A32",
  muted: "#3F5146",
  paper: "#F6F3E8",
  white: "#FFFDF6",
  green: "#226448",
  lime: "#DAF277",
  pink: "#F6A9D0",
  orange: "#F7AE64",
  line: "#DFE3D5",
  danger: "#A32942",
};
export const styles = StyleSheet.create({
  title: {
    fontSize: 32,
    fontWeight: "800",
    color: colors.ink,
    letterSpacing: -1,
  },
  h2: { fontSize: 21, fontWeight: "700", color: colors.ink },
  body: { fontSize: 15, lineHeight: 23, color: colors.ink },
  muted: { fontSize: 13, lineHeight: 20, color: colors.muted },
  card: {
    backgroundColor: colors.white,
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 12,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  input: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: "#ABB8A8",
    borderRadius: 14,
    padding: 14,
    fontSize: 16,
    color: colors.ink,
    minHeight: 50,
  },
  stack: { gap: 16 },
});
export function Card({
  children,
  color,
}: {
  children: ReactNode;
  color?: string;
}) {
  return (
    <View style={[styles.card, color ? { backgroundColor: color } : {}]}>
      {children}
    </View>
  );
}
export function Button({
  label,
  onPress,
  secondary = false,
  busy = false,
  disabled = false,
  danger = false,
}: {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  busy?: boolean;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 48,
        borderRadius: 16,
        paddingHorizontal: 18,
        paddingVertical: 13,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: danger
          ? colors.danger
          : secondary
            ? colors.lime
            : colors.green,
        opacity: disabled || busy ? 0.6 : pressed ? 0.8 : 1,
      })}
    >
      {busy ? (
        <ActivityIndicator color={secondary ? colors.ink : colors.white} />
      ) : (
        <Text
          style={{
            fontSize: 15,
            fontWeight: "700",
            color: secondary ? colors.ink : colors.white,
          }}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ gap: 7 }}>
      <Text style={[styles.body, { fontWeight: "600" }]}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.muted}
        {...props}
        style={[styles.input, props.style]}
      />
    </View>
  );
}
export function ErrorBox({ message }: { message: string | null }) {
  return message ? (
    <View
      accessibilityRole="alert"
      style={{ padding: 14, borderRadius: 14, backgroundColor: "#FFE8E9" }}
    >
      <Text style={{ color: colors.danger, lineHeight: 21 }}>{message}</Text>
    </View>
  ) : null;
}
export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <Card>
      <Text style={styles.h2}>{title}</Text>
      <Text style={styles.muted}>{detail}</Text>
    </Card>
  );
}
export function Progress({ value, label }: { value: number; label: string }) {
  const percent = Math.max(0, Math.min(100, value));
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: percent }}
      style={{
        height: 9,
        borderRadius: 8,
        backgroundColor: "#E3E7D7",
        overflow: "hidden",
      }}
    >
      <View
        style={{
          height: 9,
          width: `${percent}%`,
          backgroundColor: value > 100 ? colors.danger : colors.green,
          borderRadius: 8,
        }}
      />
    </View>
  );
}
export function Choices<T extends string>({
  items,
  value,
  onChange,
}: {
  items: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {items.map((item) => (
        <Pressable
          key={item.id}
          accessibilityRole="button"
          accessibilityState={{ selected: value === item.id }}
          onPress={() => onChange(item.id)}
          style={{
            minHeight: 44,
            paddingHorizontal: 15,
            paddingVertical: 12,
            borderRadius: 24,
            backgroundColor: value === item.id ? colors.green : "#E9ECDf",
          }}
        >
          <Text
            style={{
              color: value === item.id ? colors.white : colors.ink,
              fontWeight: "600",
            }}
          >
            {item.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}
export function Sheet({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const { width } = useWindowDimensions();
  return (
    <Modal animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{
              padding: 24,
              gap: 20,
              width: "100%",
              maxWidth: 680,
              alignSelf: "center",
              paddingBottom: 48,
            }}
          >
            <View style={styles.row}>
              <Text
                accessibilityRole="header"
                style={[
                  styles.title,
                  { flex: 1, fontSize: width < 360 ? 25 : 30 },
                ]}
              >
                {title}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Fechar formulário"
                onPress={onClose}
                style={{ padding: 14 }}
              >
                <Text style={styles.body}>Fechar</Text>
              </Pressable>
            </View>
            {children}
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  );
}
export function Confirm({
  message,
  onConfirm,
  onClose,
}: {
  message: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  return (
    <Sheet title="Excluir registro?" onClose={onClose}>
      <Text style={styles.body}>{message}</Text>
      <ErrorBox message={error} />
      <Button
        label="Excluir"
        danger
        busy={busy}
        onPress={() => {
          setBusy(true);
          onConfirm()
            .then(onClose)
            .catch((e) => setError(e.message))
            .finally(() => setBusy(false));
        }}
      />
      <Button label="Manter registro" secondary onPress={onClose} />
    </Sheet>
  );
}
