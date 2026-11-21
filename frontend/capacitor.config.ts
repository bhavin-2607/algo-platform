import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'org.dpdns.pyregex.algo',
  appName: 'Algo Mobile',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    cleartext: true,
    allowNavigation: [
      'pyregex.dpdns.org',
      '*.dpdns.org',
      '192.168.*',
      '10.*',
      'localhost',
    ],
  },
  android: {
    allowMixedContent: true,
    captureInput: true,
    webContentsDebuggingEnabled: true,
  },
};

export default config;
