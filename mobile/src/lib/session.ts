import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import { Platform } from "react-native";

let webDevice = Crypto.randomUUID();
export const vault = {
  get: (key: string) =>
    Platform.OS === "web"
      ? Promise.resolve(null)
      : SecureStore.getItemAsync(key),
  set: (key: string, value: string) =>
    Platform.OS === "web"
      ? Promise.resolve()
      : SecureStore.setItemAsync(key, value),
  remove: (key: string) =>
    Platform.OS === "web"
      ? Promise.resolve()
      : SecureStore.deleteItemAsync(key),
};
let devicePromise: Promise<string> | undefined;
export function deviceId() {
  if (!devicePromise)
    devicePromise = (async () => {
      if (Platform.OS === "web") return webDevice;
      let id = await vault.get("device");
      if (!id) {
        id = Crypto.randomUUID();
        await vault.set("device", id);
      }
      return id;
    })();
  return devicePromise;
}
