import { Platform } from 'react-native';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { api } from './api';

export async function registerPush() {
  if (Platform.OS === 'web' || !Device.isDevice)
    throw new Error('Ative os lembretes em uma build instalada no seu celular.');
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) throw new Error('O projeto de notificações ainda não foi configurado.');
  if (Platform.OS === 'android') await Notifications.setNotificationChannelAsync('advisor', {
    name: 'Lembretes de metas', importance: Notifications.AndroidImportance.DEFAULT,
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PRIVATE,
  });
  let permission = await Notifications.getPermissionsAsync();
  if (permission.status !== 'granted') permission = await Notifications.requestPermissionsAsync();
  if (permission.status !== 'granted') throw new Error('Permissão de notificações não concedida.');
  const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
  await api('/advisor/devices', 'POST', { token: data });
}

export function observeAdviceNotification(open: () => void) {
  if (Platform.OS === 'web') return () => {};
  const handle = (r: Notifications.NotificationResponse | null) => {
    if (r?.notification.request.content.data?.screen === 'advisor') open();
  };
  void Notifications.getLastNotificationResponseAsync().then(handle);
  const listener = Notifications.addNotificationResponseReceivedListener(handle);
  return () => listener.remove();
}
