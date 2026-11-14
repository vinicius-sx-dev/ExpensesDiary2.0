const base = require('./app.json').expo;
module.exports = {
  ...base,
  plugins: [...base.plugins, 'expo-notifications'],
  extra: { eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID || '' } },
  android: { ...base.android, ...(process.env.GOOGLE_SERVICES_FILE ? { googleServicesFile: process.env.GOOGLE_SERVICES_FILE } : {}) },
};


const isWindows = process.platform === 'win32';

module.exports = ({ config }) => ({
  ...config,
  plugins: [
    ...(config.plugins ?? []),
    [
      'expo-build-properties',
      {
        android: isWindows
          ? { cmakeVersion: '3.31.6' }
          : {},
      },
    ],
  ],
});
