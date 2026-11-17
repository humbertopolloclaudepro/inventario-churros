# APK de EasyStock (Android)

El APK es una app nativa de Android (hecha con [Capacitor](https://capacitorjs.com)) que abre la
app web del servidor (`/app/`) a pantalla completa, con permiso de cámara para escanear códigos
y tomar las fotos de los productos.

Las pantallas viven en el servidor (`pwa/`). Si cambias una pantalla y publicas el servidor, los
celulares ven el cambio al abrir la app, **sin instalar un APK nuevo**. Solo hay que compilar otro
APK si cambia algo de esta carpeta o la dirección del servidor.

## Compilar el APK (en GitHub, sin instalar nada)

1. Publica el servidor (ver "Desplegar" en el README) y copia su dirección, p. ej. `https://easystock.onrender.com`.
2. En GitHub: **Settings > Secrets and variables > Actions > Variables > New repository variable**
   - Nombre: `APP_URL`
   - Valor: la dirección del paso 1 (con `https://`, sin `/app/`).
3. Ve a **Actions > APK Android > Run workflow**.
4. Cuando termine (5–8 min), el APK queda en **Releases** (columna derecha del repositorio) como
   `EasyStock-1.0.N.apk`. Ábrelo desde el celular o mándalo por WhatsApp.

Cada compilación sube el número de versión, así que el APK nuevo se instala **encima** del anterior.

## Llave de firma

Android solo deja actualizar una app si el APK nuevo está firmado con la misma llave que el instalado.

- Por defecto se usa `firma/piloto.jks` (contraseña `easystock-piloto`). Sirve para el piloto,
  pero como el repositorio es público, cualquiera podría firmar un APK "falso" con ella.
- Para producción, crea una llave propia y guárdala como secretos de GitHub
  (**Settings > Secrets and variables > Actions > Secrets**):
  - `ANDROID_KEYSTORE_BASE64`: el archivo `.jks` en base64 (`base64 -w0 mi-llave.jks`)
  - `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`

  Ojo: al cambiar de llave hay que desinstalar la app vieja una vez.

## Compilar en tu computadora (opcional)

Necesitas Node 22+, JDK 21 y Android Studio (o el Android SDK).

```bash
cd android-app
npm ci
node configurar.js https://tu-servidor.onrender.com
npx cap sync android
cd android && ./gradlew assembleRelease
# El APK queda en android/app/build/outputs/apk/release/app-release.apk
```

Para probar con tu `runserver`, expón tu computadora con un túnel HTTPS (ngrok o Cloudflare Tunnel)
y usa esa dirección en `configurar.js`.

## Qué hay aquí

- `configurar.js` — escribe `capacitor.config.json` con la dirección del servidor.
- `www/index.html` — pantalla de "Sin conexión" si el servidor no responde.
- `android/` — proyecto Android. Ícono y pantalla de inicio con el logo de EasyStock,
  permiso de cámara en `AndroidManifest.xml`, firma y versión en `app/build.gradle`.
- `firma/piloto.jks` — llave de firma del piloto.
