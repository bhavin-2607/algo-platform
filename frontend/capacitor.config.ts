import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'org.dpdns.pyregex.algo',
  appName: 'Algo Mobile',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    cleartext: false,
    allowNavigation: [
      'pyregex.dpdns.org',
      '*.dpdns.org',
      '192.168.*',
      '10.*',
      'localhost',
    ],
  },
  android: {
    allowMixedContent: false,
    captureInput: true,
    webContentsDebuggingEnabled: false,
  },
  plugins: {
    StatusBar: {
      overlaysWebView: false,
      style: 'DARK',
      backgroundColor: '#0B1933',
    },
  },
};

export default config;
