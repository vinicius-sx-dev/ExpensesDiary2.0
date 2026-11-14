const base = require('./app.json').expo;
module.exports = {
  ...base,
  plugins: [...base.plugins, 'expo-notifications'],
  extra: { eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID || '' } },
  android: { ...base.android, ...(process.env.GOOGLE_SERVICES_FILE ? { googleServicesFile: process.env.GOOGLE_SERVICES_FILE } : {}) },
};
