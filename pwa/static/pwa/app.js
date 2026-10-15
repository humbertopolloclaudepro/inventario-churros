/* App del piso de venta: buscar, escanear, registrar entradas/salidas y dar de alta productos.
   JavaScript sin frameworks a propósito: un solo archivo fácil de leer y cambiar. */
"use strict";

const ES_ADMIN = document.body.dataset.admin === "1";
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const MOTIVOS = {
  entrada: [["compra", "Compra a proveedor"], ["devolucion_cliente", "Devolución de cliente"]],
  salida: [["venta", "Venta"], ["merma", "Merma o daño"], ["devolucion_proveedor", "Devolución a proveedor"]],
};

const estado = {
  catalogo: { categorias: [], marcas: [], modelos: [] },
  ubicaciones: [],
  variantes: new Map(), // id -> variante mostrada en pantalla
  mov: null, // { variante, tipo }
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

async function api(ruta, { method = "GET", body } = {}) {
  const r = await fetch(`/api/${ruta}`, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: body ? JSON.stringify(body) : undefined,
  });
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

/* ---------- tarjetas de producto ---------- */

function tarjeta(v) {
  const ubicaciones = v.existencias.length
    ? v.existencias.map((e) => `
        <li><span class="ubic">${esc(e.ubicacion.nombre)}</span><span class="cant">${piezas(e.cantidad)}</span></li>`).join("")
    : '<li class="sin-stock">Sin stock</li>';
  const costo = v.costo !== undefined ? ` · Costo $${esc(v.costo)}` : "";
  return `
    <article class="tarjeta" data-id="${v.id}">
      <h3>${esc(v.descripcion)}</h3>
      <p class="sub">${esc(v.codigo_barras)} · Total: <b>${v.stock_total}</b> · $${esc(v.precio)}${costo}</p>
      <ul class="ubicaciones">${ubicaciones}</ul>
      <div class="fila">
        <button class="boton" type="button" data-accion="entrada">Entrada</button>
        <button class="boton primario" type="button" data-accion="salida" ${v.stock_total ? "" : "disabled"}>Salida</button>
      </div>
    </article>`;
}

function mostrarVariantes(contenedor, variantes, textoVacio = "Sin resultados.") {
  variantes.forEach((v) => estado.variantes.set(v.id, v));
  contenedor.innerHTML = variantes.length
    ? variantes.map(tarjeta).join("")
    : `<p class="vacio">${esc(textoVacio)}</p>`;
}

function actualizarVariante(v) {
  estado.variantes.set(v.id, v);
  $$(`article.tarjeta[data-id="${v.id}"]`).forEach((el) => { el.outerHTML = tarjeta(v); });
}

/* ---------- navegación ---------- */

function mostrarVista(nombre) {
  $$(".vista").forEach((s) => s.classList.toggle("activa", s.id === `vista-${nombre}`));
  $$(".pestanas button").forEach((b) => b.classList.toggle("activa", b.dataset.vista === nombre));
  if (nombre !== "escanear") detenerEscaner();
  if (nombre === "buscar") $("#q").focus();
}

/* ---------- buscar ---------- */

let consulta = 0;
let temporizadorBusqueda;
$("#q").addEventListener("input", (e) => {
  clearTimeout(temporizadorBusqueda);
  const q = e.target.value.trim();
  temporizadorBusqueda = setTimeout(() => buscar(q), 250);
});

async function buscar(q) {
  const cont = $("#resultados");
  if (q.length < 2) {
    cont.innerHTML = '<p class="vacio">Escribe al menos 2 letras o escanea un código.</p>';
    return;
  }
  const mia = ++consulta;
  try {
    const variantes = await api(`buscar/?q=${encodeURIComponent(q)}`);
    if (mia === consulta) mostrarVariantes(cont, variantes, `Nada para "${q}". ¿Lo das de alta?`);
  } catch (err) {
    aviso(err.message, "error");
  }
}

/* ---------- escanear ---------- */

let lector = null;
let escaneando = false;

async function iniciarEscaner() {
  if (escaneando) return detenerEscaner();
  if (!window.Html5Qrcode) {
    aviso("No se pudo cargar el lector de códigos. Revisa tu conexión.", "error");
    return;
  }
  const F = window.Html5QrcodeSupportedFormats;
  lector = lector || new window.Html5Qrcode("lector", {
    verbose: false,
    formatsToSupport: [F.QR_CODE, F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128],
  });
  try {
    await lector.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 260, height: 160 } }, alLeer);
    escaneando = true;
    $("#btn-escanear").textContent = "Detener cámara";
  } catch (err) {
    aviso(`No se pudo abrir la cámara: ${err}`, "error");
  }
}

async function detenerEscaner() {
  if (lector && escaneando) {
    try { await lector.stop(); } catch { /* ya estaba detenido */ }
  }
  escaneando = false;
  $("#btn-escanear").textContent = "Activar cámara";
}

async function alLeer(texto) {
  await detenerEscaner();
  if (navigator.vibrate) navigator.vibrate(80);
  resolverCodigo(texto.trim());
}

async function resolverCodigo(codigo) {
  const cont = $("#resultado-escaneo");
  cont.innerHTML = `<p class="vacio">Buscando ${esc(codigo)}…</p>`;
  try {
    const d = await api(`codigo/?c=${encodeURIComponent(codigo)}`);
    if (d.tipo === "variante") {
      mostrarVariantes(cont, [d.variante]);
    } else if (d.tipo === "ubicacion") {
      const filas = d.contenido.map((c) =>
        `<li><span>${esc(c.descripcion)}</span><span class="cant">${piezas(c.cantidad)}</span></li>`).join("");
      cont.innerHTML = `
        <article class="tarjeta">
          <h3>${esc(d.ubicacion.nombre)}</h3>
          <ul class="ubicaciones">${filas || '<li class="sin-stock">Vacía</li>'}</ul>
        </article>`;
    }
  } catch (err) {
    if (err.status === 404) {
      cont.innerHTML = `
        <article class="tarjeta nuevo">
          <h3>Código nuevo</h3>
          <p class="sub">${esc(codigo)} no está registrado.</p>
          <button class="boton primario" type="button" data-alta="${esc(codigo)}">Dar de alta</button>
        </article>`;
    } else {
      cont.innerHTML = "";
      aviso(err.message, "error");
    }
  }
}

$("#btn-escanear").addEventListener("click", iniciarEscaner);
$("#form-codigo-manual").addEventListener("submit", (e) => {
  e.preventDefault();
  const codigo = $("#codigo-manual").value.trim();
  if (codigo) resolverCodigo(codigo);
});

/* ---------- movimientos (entrada / salida) ---------- */

function opciones(lista, seleccionado) {
  return lista.map(([valor, texto]) =>
    `<option value="${esc(valor)}" ${String(valor) === String(seleccionado) ? "selected" : ""}>${esc(texto)}</option>`).join("");
}

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
  cantidad.select();
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
    actualizarVariante(r.variante);
    aviso(`${tipo === "salida" ? "Salida" : "Entrada"} registrada. Quedan ${piezas(r.variante.stock_total)}.`);
  } catch (err) {
    aviso(err.message, "error");
  } finally {
    boton.disabled = false;
  }
});

/* ---------- alta rápida ---------- */

function llenarSelect(sel, items, { seleccionado, vacio } = {}) {
  const lista = items.map((i) => [i.id, i.nombre]);
  sel.innerHTML = (vacio ? `<option value="">${esc(vacio)}</option>` : "") + opciones(lista, seleccionado);
}

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
  llenarSelect($("#alta-ubicacion"), estado.ubicaciones, { vacio: "Elige ubicación" });
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

$("#form-alta").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(new FormData(form));
  body.cantidad = Number(body.cantidad || 0);
  body.ubicacion = body.ubicacion ? Number(body.ubicacion) : null;
  if (!body.costo) delete body.costo;
  if (body.cantidad > 0 && !body.ubicacion) return aviso("Elige en qué ubicación se guardan las piezas.", "error");

  const boton = form.querySelector('button[type="submit"]');
  boton.disabled = true;
  try {
    const r = await api("alta-rapida/", { method: "POST", body });
    mostrarVariantes($("#resultado-alta"), [r.variante]);
    aviso("Producto guardado.");
    // Se conservan categoría, marca, modelo, producto, precio y ubicación para capturar el siguiente color rápido.
    form.codigo_barras.value = "";
    form.color.value = "";
    form.cantidad.value = 1;
    form.codigo_barras.focus();
  } catch (err) {
    aviso(err.message, "error");
  } finally {
    boton.disabled = false;
  }
});

function irAlta(codigo) {
  $("#alta-codigo").value = codigo || "";
  $("#resultado-alta").innerHTML = "";
  mostrarVista("alta");
}

/* ---------- eventos globales ---------- */

document.addEventListener("click", (e) => {
  const pestana = e.target.closest(".pestanas button");
  if (pestana) return mostrarVista(pestana.dataset.vista);

  const accion = e.target.closest("[data-accion]");
  if (accion) {
    const id = Number(accion.closest("article.tarjeta").dataset.id);
    return abrirMovimiento(estado.variantes.get(id), accion.dataset.accion);
  }

  const alta = e.target.closest("[data-alta]");
  if (alta) irAlta(alta.dataset.alta);
});

/* ---------- arranque ---------- */

(async function iniciar() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* sin service worker: la app sigue funcionando */ });
  }
  try {
    await Promise.all([cargarCatalogo(), cargarUbicaciones()]);
  } catch (err) {
    aviso(`No se pudieron cargar los catálogos: ${err.message}`, "error");
  }
})();

void ES_ADMIN; // Disponible para mostrar u ocultar funciones de administrador.
