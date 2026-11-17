// Escribe capacitor.config.json con la dirección del servidor que abrirá el APK.
// Uso: node configurar.js https://tu-app.onrender.com
// GitHub Actions lo corre con la variable APP_URL del repositorio.
"use strict";
const fs = require("fs");
const path = require("path");

const url = (process.argv[2] || process.env.APP_URL || "").trim().replace(/\/+$/, "");
if (!/^https:\/\/[^/\s]+/.test(url)) {
  console.error(
    "Falta la dirección del servidor (debe empezar con https://).\n" +
    "En GitHub: Settings > Secrets and variables > Actions > Variables > New variable: APP_URL"
  );
  process.exit(1);
}
const host = new URL(url).host;

const config = {
  appId: "com.churrosrellenos.easystock",
  appName: "EasyStock",
  webDir: "www",
  server: {
    url: `${url}/app/`,
    // Solo este dominio se abre dentro de la app; cualquier otro enlace se abre en el navegador.
    allowNavigation: [host],
    errorPath: "index.html",
  },
  android: {
    allowMixedContent: false,
    captureInput: true,
    webContentsDebuggingEnabled: false,
  },
};

fs.writeFileSync(path.join(__dirname, "capacitor.config.json"), JSON.stringify(config, null, 2) + "\n");
console.log(`APK configurado para abrir ${config.server.url}`);
