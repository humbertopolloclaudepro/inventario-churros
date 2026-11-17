/* App del piso de venta con el formato EasyStock: inventario, escanear, producto, nuevo producto y auditoría.
   JavaScript sin frameworks a propósito: un solo archivo fácil de leer y cambiar. */
"use strict";

const ES_ADMIN = document.body.dataset.admin === "1";
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const icono = (nombre) => `<svg aria-hidden="true"><use href="#i-${nombre}"/></svg>`;

const MOTIVOS = {
  entrada: [["compra", "Compra a proveedor"], ["devolucion_cliente", "Devolución de cliente"]],
  salida: [["venta", "Venta"], ["merma", "Merma o daño"], ["devolucion_proveedor", "Devolución a proveedor"]],
};

const estado = {
  catalogo: { categorias: [], marcas: [], modelos: [] },
  ubicaciones: [],
  variantes: new Map(), // id -> variante mostrada en pantalla
  producto: null, // id de la variante abierta en la pantalla Producto
  mov: null, // { variante, tipo }
  fotoAlta: null, // Blob listo para subir después de guardar el producto nuevo
};

/* ---------- utilidades ---------- */

function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function csrf() {
  const c = document.cookie.split("; ").find((x) => x.startsWith("csrftoken="));
  return c ? decodeURIComponent(c.split("=")[1]) : "";
}

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
}

function mensajeError(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  return Object.entries(data).map(([k, v]) => `${k}: ${[].concat(v).join(" ")}`).join(" · ");
}

async function api(ruta, { method = "GET", body, formData } = {}) {
  let r;
  try {
    r = await fetch(`/api/${ruta}`, {
      method,
      credentials: "same-origin",
      headers: formData ? { "X-CSRFToken": csrf() } : { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: formData || (body ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new Error("Sin conexión a internet. Revisa el Wi-Fi o los datos e intenta de nuevo.");
  }
  let data = null;
  try { data = await r.json(); } catch { /* respuesta sin JSON */ }
  if (r.status === 403 && /credencial|autentic|credential/i.test(mensajeError(data))) {
    location.href = "/login/?next=/app/";
  }
  if (!r.ok) {
    const error = new Error(mensajeError(data) || `Error ${r.status}`);
    error.status = r.status;
    error.data = data;
    throw error;
  }
  return data;
}

let temporizadorAviso;
function aviso(texto, tipo = "ok") {
  const el = $("#aviso");
  el.textContent = texto;
  el.className = `aviso ${tipo}`;
  el.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => { el.hidden = true; }, tipo === "error" ? 5000 : 2500);
}

function piezas(n) {
  return `${n} pza${n === 1 ? "" : "s"}`;
}

function opciones(lista, seleccionado) {
  return lista.map(([valor, texto]) =>
    `<option value="${esc(valor)}" ${String(valor) === String(seleccionado) ? "selected" : ""}>${esc(texto)}</option>`).join("");
}

function llenarSelect(sel, items, { seleccionado, vacio } = {}) {
  const lista = items.map((i) => [i.id, i.nombre]);
  sel.innerHTML = (vacio ? `<option value="">${esc(vacio)}</option>` : "") + opciones(lista, seleccionado);
}

/* ---------- navegación entre pantallas ----------
   Cada pantalla se guarda en el historial, así el botón "atrás" de Android regresa a la anterior. */

const PANTALLAS = ["inicio", "escanear", "producto", "alta", "auditar"];

function mostrarPantalla(nombre) {
  if (!PANTALLAS.includes(nombre)) nombre = "inicio";
  $$(".pantalla").forEach((s) => s.classList.toggle("activa", s.id === `p-${nombre}`));
  $("#menu").hidden = true;
  if (nombre !== "escanear") escaner.detener();
  if (nombre !== "auditar") escanerAud.detener();
  if (nombre === "escanear") { $("#resultado-escaneo").innerHTML = ""; escaner.iniciar(); }
  if (nombre === "auditar") cargarAuditorias();
  if (nombre === "inicio") cargarInventario();
  window.scrollTo(0, 0);
}

function ir(nombre, { reemplazar = false } = {}) {
  history[reemplazar ? "replaceState" : "pushState"]({ p: nombre }, "", `#${nombre}`);
  mostrarPantalla(nombre);
}

window.addEventListener("popstate", (e) => {
  if ($("#dlg-mov").open) $("#dlg-mov").close();
  mostrarPantalla(e.state?.p || "inicio");
});

/* ---------- inicio: inventario ---------- */

function miniatura(v) {
  return v.foto_url
    ? `<img src="${esc(v.foto_url)}" alt="" loading="lazy">`
    : icono("sin-foto");
}

function itemInventario(v) {
  const principal = v.existencias[0];
  const otras = v.existencias.length > 1 ? ` +${v.existencias.length - 1}` : "";
  const ubic = principal
    ? `${icono("ubicacion")}${esc(principal.ubicacion.nombre)}${otras}`
    : "Sin stock";
  return `
    <button class="item" type="button" data-producto="${v.id}">
      <span class="miniatura">${miniatura(v)}</span>
      <span class="item-texto"><b>${esc(v.descripcion)}</b><span class="item-ubic">${ubic}</span></span>
      <span class="item-stock${v.stock_total ? "" : " agotado"}"><b>${v.stock_total}</b><span>pzs</span></span>
    </button>`;
}

let consulta = 0;
async function cargarInventario() {
  const q = $("#q").value.trim();
  const orden = $("#orden").value;
  const mia = ++consulta;
  try {
    const d = await api(`inventario/?orden=${encodeURIComponent(orden)}&q=${encodeURIComponent(q)}`);
    if (mia !== consulta) return;
    d.variantes.forEach((v) => estado.variantes.set(v.id, v));
    const cont = $("#inv-lista");
    if (!d.variantes.length) {
      cont.innerHTML = q
        ? `<p class="vacio corto">Nada para "${esc(q)}".</p>
           <div class="fila centrada"><button class="boton tonal" type="button" data-ir="alta">Dar de alta</button></div>`
        : '<p class="vacio">Inventario vacío</p>';
      $("#inv-total").textContent = "";
      return;
    }
    cont.innerHTML = d.variantes.map(itemInventario).join("");
    const mostrados = d.variantes.length < d.total ? ` (se muestran ${d.variantes.length})` : "";
    $("#inv-total").textContent = `${d.total} producto${d.total === 1 ? "" : "s"}${mostrados}`;
  } catch (err) {
    if (mia === consulta) aviso(err.message, "error");
  }
}

let temporizadorBusqueda;
$("#q").addEventListener("input", () => {
  clearTimeout(temporizadorBusqueda);
  temporizadorBusqueda = setTimeout(cargarInventario, 250);
});
$("#orden").addEventListener("change", cargarInventario);

$("#btn-menu").addEventListener("click", (e) => {
  e.stopPropagation();
  $("#menu").hidden = !$("#menu").hidden;
});

/* ---------- producto ---------- */

function pintarProducto(v) {
  estado.variantes.set(v.id, v);
  estado.producto = v.id;
  const ubicaciones = v.existencias.length
    ? v.existencias.map((e) => `
        <li><span class="ubic">${icono("ubicacion")}${esc(e.ubicacion.nombre)}</span><span class="cant">${piezas(e.cantidad)}</span></li>`).join("")
    : '<li class="sin-stock">Sin stock en ninguna ubicación</li>';
  const chips = [v.categoria, v.marca, v.modelo, v.color, v.material].filter(Boolean)
    .map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  const costo = v.costo !== undefined
    ? `<div class="dato"><span>Costo</span><b>$${esc(v.costo)}</b></div>` : "";
  $("#producto-detalle").innerHTML = `
    <div class="detalle">
      <p class="sku">SKU: ${esc(v.codigo_barras)}</p>
      <div class="foto">${v.foto_url ? `<img src="${esc(v.foto_url)}" alt="Foto de ${esc(v.descripcion)}">` : icono("sin-foto")}</div>
      <div class="fila centrada">
        <label class="boton tonal chico">${icono("camara")}Cámara
          <input type="file" accept="image/*" capture="environment" data-foto="producto" hidden></label>
        <label class="boton tonal chico">${icono("galeria")}Galería
          <input type="file" accept="image/*" data-foto="producto" hidden></label>
      </div>
      <h2>${esc(v.descripcion)}</h2>
      <div class="chips">${chips}</div>
      <div class="datos">
        <div class="dato"><span>En tienda</span><b>${piezas(v.stock_total)}</b></div>
        <div class="dato"><span>Precio</span><b>$${esc(v.precio)}</b></div>
        ${costo}
      </div>
      <p class="titulo-foto">Dónde está</p>
      <ul class="ubicaciones">${ubicaciones}</ul>
      <div class="fila">
        <button class="boton tonal" type="button" data-accion="entrada">Entrada</button>
        <button class="boton primario" type="button" data-accion="salida" ${v.stock_total ? "" : "disabled"}>Salida / Venta</button>
      </div>
    </div>`;
}

function abrirProducto(v) {
  pintarProducto(v);
  ir("producto");
}

/* ---------- fotos ---------- */

/** Reduce la foto en el celular antes de subirla: sube rápido aunque la señal sea mala. */
async function reducirFoto(archivo, lado = 1280) {
  try {
    const imagen = await createImageBitmap(archivo, { imageOrientation: "from-image" });
    const escala = Math.min(1, lado / Math.max(imagen.width, imagen.height));
    const lienzo = document.createElement("canvas");
    lienzo.width = Math.round(imagen.width * escala);
    lienzo.height = Math.round(imagen.height * escala);
    lienzo.getContext("2d").drawImage(imagen, 0, 0, lienzo.width, lienzo.height);
    const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", 0.85));
    return blob || archivo;
  } catch {
    return archivo; // El servidor la reduce de todos modos.
  }
}

async function subirFoto(idVariante, blob) {
  const datos = new FormData();
  datos.append("foto", blob, "foto.jpg");
  const r = await api(`variantes/${idVariante}/foto/`, { method: "POST", formData: datos });
  return r.variante;
}

function vistaPrevia(contenedor, blob) {
  const url = URL.createObjectURL(blob);
  contenedor.innerHTML = `<img src="${url}" alt="Vista previa">`;
}

document.addEventListener("change", async (e) => {
  const entrada = e.target.closest("input[data-foto]");
  if (!entrada || !entrada.files.length) return;
  const archivo = entrada.files[0];
  entrada.value = ""; // Permite elegir la misma foto otra vez.
  const blob = await reducirFoto(archivo);

  if (entrada.dataset.foto === "alta") {
    estado.fotoAlta = blob;
    vistaPrevia($("#alta-foto"), blob);
    return;
  }
  // Foto de un producto existente: se sube de inmediato.
  vistaPrevia($("#producto-detalle .foto"), blob);
  try {
    const v = await subirFoto(estado.producto, blob);
    pintarProducto(v);
    aviso("Foto guardada.");
  } catch (err) {
    aviso(err.message, "error");
  }
});

/* ---------- escáner (componente reutilizable) ---------- */

class Escaner {
  /**
   * idContenedor: div donde se dibuja el video. boton: el botón que lo enciende/apaga.
   * alLeer(codigo): qué hacer con cada código leído.
   * continuo: si es true, la cámara sigue encendida y hace una pausa breve entre lecturas
   *           (para contar varias piezas seguidas); si es false, se apaga al leer.
   */
  constructor(idContenedor, boton, alLeer, { continuo = false } = {}) {
    this.id = idContenedor;
    this.boton = boton;
    this.textoBoton = boton.textContent;
    this.alLeer = alLeer;
    this.continuo = continuo;
    this.lector = null;
    this.activo = false;
    this.iniciando = false;
    this.pausado = false;
  }

  async alternar() {
    return this.activo ? this.detener() : this.iniciar();
  }

  async iniciar() {
    if (this.activo || this.iniciando) return;
    if (!window.Html5Qrcode) {
      aviso("No se pudo cargar el lector de códigos. Cierra y abre la app.", "error");
      return;
    }
    this.iniciando = true;
    const F = window.Html5QrcodeSupportedFormats;
    this.lector = this.lector || new window.Html5Qrcode(this.id, {
      verbose: false,
      formatsToSupport: [F.QR_CODE, F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128, F.CODE_39],
      // Usa el lector de códigos nativo de Android cuando existe: es mucho más rápido.
      experimentalFeatures: { useBarCodeDetectorIfSupported: true },
    });
    const contenedor = document.getElementById(this.id);
    // Se muestra el contenedor ANTES de iniciar: el lector usa su ancho para dimensionar el video.
    contenedor.hidden = false;
    try {
      await this.lector.start(
        { facingMode: "environment" },
        {
          fps: 10,
          // Recuadro guía proporcional a la pantalla (sirve en celular y en computadora).
          qrbox: (ancho, alto) => ({
            width: Math.max(160, Math.floor(Math.min(ancho * 0.8, 340))),
            height: Math.max(100, Math.floor(Math.min(alto * 0.5, 200))),
          }),
        },
        (texto) => this.leido(texto)
      );
      this.activo = true;
      this.boton.textContent = "Detener cámara";
    } catch (err) {
      contenedor.hidden = true;
      aviso(`No se pudo abrir la cámara. Revisa que la app tenga permiso de cámara. (${err})`, "error");
    } finally {
      this.iniciando = false;
    }
  }

  async detener() {
    if (this.lector && this.activo) {
      try { await this.lector.stop(); } catch { /* ya estaba detenido */ }
    }
    this.activo = false;
    this.pausado = false;
    document.getElementById(this.id).hidden = true;
    this.boton.textContent = this.textoBoton;
  }

  async leido(texto) {
    if (this.pausado) return;
    if (navigator.vibrate) navigator.vibrate(80);
    if (!this.continuo) {
      await this.detener();
    } else {
      // Congela la imagen un momento: da tiempo de retirar la pieza y evita contarla dos veces.
      this.pausado = true;
      try { this.lector.pause(true); } catch { /* sin soporte de pausa */ }
      setTimeout(() => {
        if (!this.activo) return;
        try { this.lector.resume(); } catch { /* ya se detuvo */ }
        this.pausado = false;
      }, 1200);
    }
    this.alLeer(texto.trim());
  }
}

/* ---------- escanear ---------- */

async function resolverCodigo(codigo) {
  const cont = $("#resultado-escaneo");
  cont.innerHTML = `<p class="vacio corto">Buscando ${esc(codigo)}…</p>`;
  try {
    const d = await api(`codigo/?c=${encodeURIComponent(codigo)}`);
    if (d.tipo === "variante") {
      cont.innerHTML = "";
      pintarProducto(d.variante);
      ir("producto", { reemplazar: true }); // "atrás" desde el producto regresa al inventario
    } else if (d.tipo === "ubicacion") {
      const filas = d.contenido.map((c) =>
        `<li><span>${esc(c.descripcion)}</span><span class="cant">${piezas(c.cantidad)}</span></li>`).join("");
      cont.innerHTML = `
        <article class="tarjeta">
          <h3>${icono("ubicacion")} ${esc(d.ubicacion.nombre)}</h3>
          <ul class="ubicaciones">${filas || '<li class="sin-stock">Vacía</li>'}</ul>
        </article>`;
    }
  } catch (err) {
    if (err.status === 404) {
      cont.innerHTML = "";
      irAlta(codigo, { reemplazar: true });
      aviso(`El código ${codigo} es nuevo. Llena los datos del producto.`);
    } else {
      cont.innerHTML = "";
      aviso(err.message, "error");
    }
  }
}

const escaner = new Escaner("lector", $("#btn-escanear"), resolverCodigo);
$("#btn-escanear").addEventListener("click", () => escaner.alternar());
$("#form-codigo-manual").addEventListener("submit", (e) => {
  e.preventDefault();
  const codigo = $("#codigo-manual").value.trim();
  if (codigo) { escaner.detener(); resolverCodigo(codigo); }
});

/* ---------- movimientos (entrada / salida) ---------- */

function abrirMovimiento(variante, tipo) {
  estado.mov = { variante, tipo };
  $("#mov-titulo").textContent = tipo === "salida" ? "Registrar salida" : "Registrar entrada";
  $("#mov-producto").textContent = variante.descripcion;
  $("#mov-motivo").innerHTML = opciones(MOTIVOS[tipo]);
  const cantidad = $("#mov-cantidad");
  cantidad.value = 1;

  let lista;
  if (tipo === "salida") {
    lista = variante.existencias.map((e) => [e.ubicacion.id, `${e.ubicacion.nombre} (${piezas(e.cantidad)})`]);
  } else {
    lista = estado.ubicaciones.map((u) => [u.id, u.nombre]);
  }
  const preferida = variante.existencias[0]?.ubicacion.id;
  $("#mov-ubicacion").innerHTML = opciones(lista, preferida);
  $("#dlg-mov").showModal();
}

$("#mov-cancelar").addEventListener("click", () => $("#dlg-mov").close());

$("#form-mov").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { variante, tipo } = estado.mov;
  const boton = $("#mov-ok");
  boton.disabled = true;
  try {
    const r = await api("movimientos/", {
      method: "POST",
      body: {
        variante: variante.id,
        ubicacion: Number($("#mov-ubicacion").value),
        tipo,
        motivo: $("#mov-motivo").value,
        cantidad: Number($("#mov-cantidad").value),
        uuid_cliente: uuid(),
      },
    });
    $("#dlg-mov").close();
    pintarProducto(r.variante);
    aviso(`${tipo === "salida" ? "Salida" : "Entrada"} registrada. Quedan ${piezas(r.variante.stock_total)}.`);
  } catch (err) {
    aviso(err.message, "error");
  } finally {
    boton.disabled = false;
  }
});

/* Botones − y + junto a un campo numérico */
document.addEventListener("click", (e) => {
  const paso = e.target.closest("[data-paso]");
  if (!paso) return;
  const campo = document.getElementById(paso.dataset.para);
  const minimo = Number(paso.dataset.minimo ?? campo.min ?? 0);
  campo.value = Math.max(minimo, (Number(campo.value) || 0) + Number(paso.dataset.paso));
});

/* ---------- nuevo producto ---------- */

function llenarModelos(seleccionado) {
  const marca = Number($("#alta-marca").value);
  const modelos = estado.catalogo.modelos.filter((m) => m.marca === marca);
  llenarSelect($("#alta-modelo"), modelos, { seleccionado, vacio: modelos.length ? "Elige un modelo" : "Agrega un modelo con +" });
}

async function cargarCatalogo(seleccion = {}) {
  estado.catalogo = await api("catalogo/");
  const actual = {
    categoria: $("#alta-categoria").value,
    marca: $("#alta-marca").value,
    modelo: $("#alta-modelo").value,
    ...seleccion,
  };
  llenarSelect($("#alta-categoria"), estado.catalogo.categorias, { seleccionado: actual.categoria, vacio: "Elige una categoría" });
  llenarSelect($("#alta-marca"), estado.catalogo.marcas, { seleccionado: actual.marca, vacio: "Elige una marca" });
  llenarModelos(actual.modelo);
}

async function cargarUbicaciones() {
  estado.ubicaciones = await api("ubicaciones/");
  llenarSelect($("#alta-ubicacion"), estado.ubicaciones, { seleccionado: $("#alta-ubicacion").value, vacio: "Elige ubicación" });
}

$("#alta-marca").addEventListener("change", () => llenarModelos());

$$("[data-nuevo]").forEach((boton) => boton.addEventListener("click", async () => {
  const tipo = boton.dataset.nuevo;
  try {
    if (tipo === "modelo") {
      const marca = $("#alta-marca");
      if (!marca.value) return aviso("Primero elige la marca.", "error");
      const nombre = prompt(`Nuevo modelo de ${marca.selectedOptions[0].text} (p. ej. "iPhone 15 Pro")`);
      if (!nombre) return;
      const m = await api("modelos/", { method: "POST", body: { marca: Number(marca.value), nombre } });
      await cargarCatalogo({ modelo: m.id });
    } else {
      const nombre = prompt(tipo === "marca" ? "Nombre de la nueva marca" : "Nombre de la nueva categoría");
      if (!nombre) return;
      const ruta = tipo === "marca" ? "marcas/" : "categorias/";
      const item = await api(ruta, { method: "POST", body: { nombre } });
      await cargarCatalogo(tipo === "marca" ? { marca: item.id, modelo: "" } : { categoria: item.id });
    }
  } catch (err) {
    aviso(err.message, "error");
  }
}));

function limpiarFotoAlta() {
  estado.fotoAlta = null;
  $("#alta-foto").innerHTML = icono("sin-foto");
}

function irAlta(codigo, opciones_ = {}) {
  const escaneado = Boolean(codigo);
  $("#alta-codigo").value = codigo || "";
  $("#alta-sku").textContent = codigo || "";
  $("#alta-sku-texto").hidden = !escaneado;
  $("#alta-codigo-campo").hidden = escaneado;
  limpiarFotoAlta();
  ir("alta", opciones_);
}

$("#form-alta").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(new FormData(form));
  body.cantidad = Number(body.cantidad || 0);
  body.ubicacion = body.ubicacion ? Number(body.ubicacion) : null;
  if (!body.costo) delete body.costo;
  if (!body.nombre_producto.trim()) return aviso("Escribe el nombre del producto.", "error");
  if (body.precio === "") return aviso("Escribe el precio de venta.", "error");
  if (!body.categoria) return aviso("Elige la categoría.", "error");
  if (!body.modelo_telefono) return aviso("Elige la marca y el modelo de teléfono.", "error");
  if (body.cantidad > 0 && !body.ubicacion) return aviso("Elige en qué ubicación se guardan las piezas.", "error");

  const boton = form.querySelector('button[type="submit"]');
  boton.disabled = true;
  try {
    const r = await api("alta-rapida/", { method: "POST", body });
    let variante = r.variante;
    if (estado.fotoAlta) {
      try {
        variante = await subirFoto(variante.id, estado.fotoAlta);
      } catch (err) {
        aviso(`El producto se guardó, pero la foto no: ${err.message} Puedes tomarla desde el producto.`, "error");
      }
    }
    // Se conservan categoría, marca, modelo, producto, precio y ubicación para capturar el siguiente color rápido.
    form.color.value = "";
    form.cantidad.value = 1;
    limpiarFotoAlta();
    pintarProducto(variante);
    ir("producto", { reemplazar: true });
    aviso("¡Producto nuevo guardado!");
  } catch (err) {
    aviso(err.message, "error");
  } finally {
    boton.disabled = false;
  }
});

/* ---------- auditoría ---------- */
/* Contar una zona completa. Se escanea el QR de la caja y luego cada pieza que hay en ella.
   El conteo es "a ciegas": la app no muestra cuántas piezas dice el sistema. */

const aud = { actual: null, ubicacion: null };

function mostrarPaso(paso) {
  ["inicio", "conteo", "revision"].forEach((p) => { $(`#aud-${p}`).hidden = p !== paso; });
}

async function cargarAuditorias() {
  try {
    if (aud.actual) return mostrarAuditoria(await api(`auditorias/${aud.actual.id}/`));
    const d = await api("auditorias/");
    llenarSelect($("#aud-zona"), d.zonas.map((z) => ({ id: z, nombre: z })), { vacio: "Elige la zona a contar" });
    $("#aud-pendientes").innerHTML = d.en_curso.length
      ? "<h3>En curso</h3>" + d.en_curso.map((a) => `
          <article class="tarjeta">
            <h3>${esc(a.zona)}</h3>
            <p class="sub">${esc(a.estado_texto)} · iniciada por ${esc(a.creada_por)} el ${esc(a.creada)}</p>
            <div class="fila"><button class="boton tonal" type="button" data-aud-abrir="${a.id}">
              ${a.estado === "abierta" ? "Continuar conteo" : "Ver"}</button></div>
          </article>`).join("")
      : "";
    mostrarPaso("inicio");
  } catch (err) {
    aviso(err.message, "error");
  }
}

function mostrarAuditoria(d) {
  aud.actual = d;
  if (!d.ubicaciones.some((u) => u.id === aud.ubicacion)) aud.ubicacion = null;
  if (d.estado === "abierta") pintarConteo(d);
  else { escanerAud.detener(); pintarRevision(d); }
}

function pintarConteo(d) {
  $("#aud-titulo").textContent = `Contando ${d.zona}`;
  $("#aud-progreso").textContent = `${d.resumen.contadas} de ${d.resumen.lineas} productos contados`;
  llenarSelect($("#aud-ubic"), d.ubicaciones, { seleccionado: aud.ubicacion, vacio: "Escanea el QR de la caja o elígela" });

  const grupos = new Map();
  d.lineas.forEach((l) => {
    if (!grupos.has(l.ubicacion)) grupos.set(l.ubicacion, []);
    grupos.get(l.ubicacion).push(l);
  });
  $("#aud-lineas").innerHTML = grupos.size
    ? [...grupos].map(([ubic, lineas]) => `
        <section class="aud-grupo">
          <h3>${esc(ubic)}</h3>
          ${lineas.map((l) => `
            <div class="aud-linea${l.contada ? " contada" : ""}">
              <div><b>${esc(l.descripcion)}</b><br><span class="sub">${esc(l.codigo)}</span></div>
              <div class="contador" data-variante="${l.variante_id}" data-ubicacion="${l.ubicacion_id}">
                <button type="button" class="paso menos" data-aud="menos" aria-label="Una menos">${icono("menos")}</button>
                <button type="button" class="cifra" data-aud="fijar" aria-label="Escribir cantidad">${l.contada ? l.contado : "—"}</button>
                <button type="button" class="paso mas" data-aud="mas" aria-label="Una más">${icono("mas")}</button>
              </div>
            </div>`).join("")}
        </section>`).join("")
    : '<p class="vacio corto">El sistema no tiene piezas en esta zona. Escanea lo que encuentres.</p>';
  mostrarPaso("conteo");
}

function pintarRevision(d) {
  const r = d.resumen;
  let html = `<h2>${esc(d.zona)}</h2><p class="sub">${esc(d.estado_texto)}${d.minutos != null ? ` · conteo de ${d.minutos} min` : ""}</p>`;
  const exactitud = (n) => (r.lineas ? Math.round((100 * (r.lineas - n)) / r.lineas) : 100);

  if (d.estado === "revision" && !d.es_admin) {
    html += "<p>Conteo enviado. Un administrador revisará las diferencias y ajustará el inventario.</p>";
  } else if (d.estado === "revision") {
    const difs = d.lineas.filter((l) => l.diferencia !== 0);
    html += `
      <ul class="ubicaciones resumen-aud">
        <li><span>Productos revisados</span><b>${r.lineas}</b></li>
        <li><span>Coinciden con el sistema</span><b>${r.lineas - r.con_diferencia} (${exactitud(r.con_diferencia)} %)</b></li>
        <li><span>Piezas faltantes</span><b class="dif-neg">${r.faltantes}</b></li>
        <li><span>Piezas sobrantes</span><b class="dif-pos">${r.sobrantes}</b></li>
      </ul>
      ${difs.length ? "<h3>Diferencias</h3>" : '<p class="vacio corto">Todo coincide. No hay nada que ajustar.</p>'}
      ${difs.map((l) => `
        <div class="aud-linea">
          <div><b>${esc(l.descripcion)}</b><br><span class="sub">${esc(l.ubicacion)}${l.contada ? "" : " · no se contó"}</span></div>
          <div class="dif">
            <span class="sub">${l.sistema} → ${l.contado}</span>
            <b class="${l.diferencia < 0 ? "dif-neg" : "dif-pos"}">${l.diferencia > 0 ? "+" : ""}${l.diferencia}</b>
          </div>
        </div>`).join("")}
      <div class="fila"><button class="boton primario" type="button" data-aud-accion="aplicar">
        ${difs.length ? "Aplicar ajustes" : "Cerrar auditoría"}</button></div>
      <div class="fila">
        <button class="boton" type="button" data-aud-accion="reabrir">Volver a contar</button>
        <button class="boton" type="button" data-aud-accion="cancelar">Cancelar auditoría</button>
      </div>`;
  } else if (d.estado === "aplicada") {
    html += `<p>El inventario de la zona quedó igual a lo contado.</p>
      <ul class="ubicaciones resumen-aud">
        <li><span>Exactitud</span><b>${exactitud(r.con_diferencia)} %</b></li>
        <li><span>Piezas faltantes ajustadas</span><b>${r.faltantes}</b></li>
        <li><span>Piezas sobrantes ajustadas</span><b>${r.sobrantes}</b></li>
      </ul>`;
  } else {
    html += "<p>Esta auditoría se canceló; el inventario no cambió.</p>";
  }
  html += '<div class="fila"><button class="boton" type="button" data-aud-accion="salir">Volver</button></div>';
  $("#aud-revision").innerHTML = html;
  mostrarPaso("revision");
}

async function contar(variante, ubicacion, cambio) {
  try {
    const r = await api(`auditorias/${aud.actual.id}/conteo/`, {
      method: "POST",
      body: { variante, ubicacion, ...cambio },
    });
    if (cambio.sumar) aviso(`+${cambio.sumar} ${r.descripcion} → ${r.contado}`);
    mostrarAuditoria(await api(`auditorias/${aud.actual.id}/`));
  } catch (err) {
    aviso(err.message, "error");
  }
}

async function contarCodigo(codigo) {
  if (!aud.actual || aud.actual.estado !== "abierta" || !codigo) return;
  let d;
  try {
    d = await api(`codigo/?c=${encodeURIComponent(codigo)}`);
  } catch (err) {
    aviso(err.status === 404 ? `El código ${codigo} no está registrado. Apártalo y dalo de alta después.` : err.message, "error");
    return;
  }
  if (d.tipo === "ubicacion") {
    if (d.ubicacion.zona !== aud.actual.zona) {
      aviso(`${d.ubicacion.nombre} no es de ${aud.actual.zona}.`, "error");
      return;
    }
    aud.ubicacion = d.ubicacion.id;
    $("#aud-ubic").value = String(aud.ubicacion);
    aviso(`Contando en ${d.ubicacion.nombre}`);
    return;
  }
  if (!aud.ubicacion) {
    aviso("Primero escanea el QR de la caja, o elígela en la lista.", "error");
    return;
  }
  await contar(d.variante.id, aud.ubicacion, { sumar: 1 });
}

const escanerAud = new Escaner("lector-aud", $("#aud-camara"), contarCodigo, { continuo: true });
$("#aud-camara").addEventListener("click", () => escanerAud.alternar());

$("#aud-ubic").addEventListener("change", (e) => { aud.ubicacion = Number(e.target.value) || null; });

$("#aud-empezar").addEventListener("click", async () => {
  const zona = $("#aud-zona").value;
  if (!zona) return aviso("Elige la zona que vas a contar.", "error");
  try {
    aud.ubicacion = null;
    mostrarAuditoria(await api("auditorias/", { method: "POST", body: { zona } }));
  } catch (err) {
    aviso(err.message, "error");
  }
});

$("#aud-manual").addEventListener("submit", (e) => {
  e.preventDefault();
  const campo = $("#aud-codigo");
  contarCodigo(campo.value.trim());
  campo.value = "";
});

$("#aud-terminar").addEventListener("click", async () => {
  const faltan = aud.actual.resumen.lineas - aud.actual.resumen.contadas;
  if (faltan > 0 && !confirm(`Hay ${faltan} producto(s) sin contar. Se tomarán como 0 piezas. ¿Terminar el conteo?`)) return;
  try {
    mostrarAuditoria(await api(`auditorias/${aud.actual.id}/terminar/`, { method: "POST" }));
  } catch (err) {
    aviso(err.message, "error");
  }
});

$("#aud-salir").addEventListener("click", () => {
  escanerAud.detener();
  aud.actual = null;
  cargarAuditorias();
});

$("#p-auditar").addEventListener("click", async (e) => {
  const abrir = e.target.closest("[data-aud-abrir]");
  if (abrir) {
    try { mostrarAuditoria(await api(`auditorias/${abrir.dataset.audAbrir}/`)); } catch (err) { aviso(err.message, "error"); }
    return;
  }

  const boton = e.target.closest("[data-aud]");
  if (boton) {
    const c = boton.closest(".contador");
    const variante = Number(c.dataset.variante), ubicacion = Number(c.dataset.ubicacion);
    const linea = aud.actual.lineas.find((l) => l.variante_id === variante && l.ubicacion_id === ubicacion);
    if (boton.dataset.aud === "mas") return contar(variante, ubicacion, { sumar: 1 });
    if (boton.dataset.aud === "menos") return contar(variante, ubicacion, { fijar: Math.max(0, linea.contado - 1) });
    const n = prompt(`¿Cuántas piezas de "${linea.descripcion}" contaste?`, linea.contada ? linea.contado : "");
    if (n === null || n.trim() === "") return;
    if (!/^\d+$/.test(n.trim())) return aviso("Escribe un número entero.", "error");
    return contar(variante, ubicacion, { fijar: Number(n) });
  }

  const accion = e.target.closest("[data-aud-accion]")?.dataset.audAccion;
  if (!accion) return;
  if (accion === "salir") {
    aud.actual = null;
    return cargarAuditorias();
  }
  const preguntas = {
    aplicar: "Se ajustará el inventario de la zona para que quede igual a lo contado. ¿Continuar?",
    cancelar: "Se descartará este conteo y el inventario no cambiará. ¿Cancelar la auditoría?",
  };
  if (preguntas[accion] && !confirm(preguntas[accion])) return;
  try {
    mostrarAuditoria(await api(`auditorias/${aud.actual.id}/${accion}/`, { method: "POST" }));
    if (accion === "aplicar") aviso("Ajustes aplicados.");
  } catch (err) {
    aviso(err.message, "error");
  }
});

/* ---------- eventos globales ---------- */

document.addEventListener("click", (e) => {
  if (!e.target.closest("#menu, #btn-menu")) $("#menu").hidden = true;

  if (e.target.closest("[data-atras]")) return history.back();

  const destino = e.target.closest("[data-ir]");
  if (destino) {
    if (destino.dataset.ir === "alta") return irAlta("");
    return ir(destino.dataset.ir);
  }

  const producto = e.target.closest("[data-producto]");
  if (producto) return abrirProducto(estado.variantes.get(Number(producto.dataset.producto)));

  const accion = e.target.closest("[data-accion]");
  if (accion) return abrirMovimiento(estado.variantes.get(estado.producto), accion.dataset.accion);
});

/* ---------- botón "atrás" de Android (dentro del APK) ---------- */

const AppNativa = window.Capacitor?.Plugins?.App;
if (AppNativa) {
  AppNativa.addListener("backButton", () => {
    if ($("#dlg-mov").open) return $("#dlg-mov").close();
    if (!$("#menu").hidden) { $("#menu").hidden = true; return; }
    if (!$("#p-inicio").classList.contains("activa")) return history.back();
    AppNativa.exitApp(); // En el inventario, "atrás" cierra la app en vez de regresar al inicio de sesión.
  });
}

/* ---------- arranque ---------- */

(async function iniciar() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* sin service worker: la app sigue funcionando */ });
  }
  history.replaceState({ p: "inicio" }, "", "#inicio");
  mostrarPantalla("inicio");
  try {
    await Promise.all([cargarCatalogo(), cargarUbicaciones()]);
  } catch (err) {
    aviso(`No se pudieron cargar los catálogos: ${err.message}`, "error");
  }
})();

void ES_ADMIN; // Disponible para mostrar u ocultar funciones de administrador.
