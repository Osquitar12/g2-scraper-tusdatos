"""
G2.com Scraper — Prueba Técnica Tusdatos.co
============================================
Extrae categorías y subcategorías reales de G2.com
- 100 iteraciones
- Sin búsqueda de productos (solo categoria, subcategoria, url)
- Retry con backoff exponencial
- Métricas completas según PDF de la prueba
- Salida: g2_dataset.csv + performance_report.json
"""

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import time
import csv
import random
import json
from datetime import datetime

BASE_URL = "https://www.g2.com/categories"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def human_delay(a=1.5, b=3.0):
    """Pausa aleatoria para simular comportamiento humano."""
    time.sleep(random.uniform(a, b))


# ── OBTENER ESTRUCTURA COMPLETA DE CATEGORÍAS ────────────
def get_structure(page):
    """
    Carga la página de categorías de G2 y extrae la estructura real del DOM:
      - Categoría principal: <td> dentro de <thead> de cada <table.categories_table>
      - Subcategorías:       <a> dentro de <div.categories_item> de cada tabla
    Toma máximo 10 subcategorías por categoría para cubrir todas las categorías.
    Retorna una lista plana de dicts sin duplicados.
    """
    print("📂 Cargando categorías de G2...")
    page.goto(BASE_URL, wait_until="networkidle", timeout=90000)

    # Esperar explícitamente a que aparezca algún contenido de categorías
    try:
        page.wait_for_selector("div.categories_item", timeout=20000)
    except Exception:
        print("   ⚠ Timeout esperando div.categories_item — intentando con scroll...")

    # Scroll completo para activar lazy-loading de todas las tablas
    for _ in range(4):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1.5)

    flat = []
    seen_urls = set()
    MAX_PER_CATEGORY = 10

    # Cada grupo de categoría está en una <table class="categories_table">
    tables = page.locator("table.categories_table")
    total_tables = tables.count()
    print(f"   → {total_tables} tablas de categorías encontradas")

    # Si aún no hay tablas, intentar fallback con div.categories_row
    if total_tables == 0:
        print("   ⚠ Fallback: buscando div.categories_row...")
        rows = page.locator("div.categories_row")
        print(f"   → {rows.count()} rows encontrados")

        # Fallback final: todos los links /categories/
        print("   ⚠ Fallback final: extrayendo todos los a[href*='/categories/']")
        links = page.locator("a[href*='/categories/']")
        seen = set()
        fallback_flat = []
        for i in range(links.count()):
            a = links.nth(i)
            try:
                href = a.get_attribute("href")
                name = a.inner_text(timeout=2000).strip()
                name = " ".join(name.split())
                if href and name and len(name) > 2 and href not in seen:
                    seen.add(href)
                    url = "https://www.g2.com" + href if href.startswith("/") else href
                    fallback_flat.append({
                        "category":    "G2 Categories",
                        "subcategory": name,
                        "url":         url,
                    })
            except Exception:
                continue
        print(f"   → {len(fallback_flat)} subcategorías por fallback")
        return fallback_flat

    for t in range(total_tables):
        table = tables.nth(t)

        # Nombre de la categoría principal está en thead > tr > td
        try:
            category = table.locator("thead td").first.inner_text(timeout=3000).strip()
            # Limpiar saltos de línea y espacios extra
            category = " ".join(category.split())
        except Exception:
            category = f"Category_{t + 1}"

        # Subcategorías: cada <div.categories_item> tiene un <a> con href y nombre
        items = table.locator("div.categories_item a[href*='/categories/']")
        count = items.count()
        added = 0

        for j in range(count):
            if added >= MAX_PER_CATEGORY:
                break
            a = items.nth(j)
            try:
                href = a.get_attribute("href")
                if not href:
                    continue
                url = "https://www.g2.com" + href if href.startswith("/") else href
                if url in seen_urls:
                    continue
                # Nombre: inner_text limpia los <font> anidados automáticamente
                name = a.inner_text(timeout=2000).strip()
                name = " ".join(name.split())
                if not name or len(name) < 2:
                    continue
                seen_urls.add(url)
                flat.append({
                    "category":    category,
                    "subcategory": name,
                    "url":         url,
                })
                added += 1
            except Exception:
                continue

        print(f"   ✓ {category}: {added}/{count} subcategorías tomadas")

    print(f"\n   📦 Total seleccionadas: {len(flat)} subcategorías únicas")
    return flat


# ── VISITA DE PÁGINA (sin búsqueda de productos) ─────────
def scrape_item(page, item):
    """
    Visita la URL de una subcategoría y extrae el título real de la página.
    Intenta primero selectores de H1 específicos de G2; si ninguno funciona,
    cae en page.title() como último recurso.

    Retorna:
        dict con page_title y page_loaded (bool)
    """
    page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
    human_delay(1.0, 2.0)

    # Scroll suave para asegurar carga de contenido lazy
    page.evaluate("window.scrollTo(0, 300)")
    time.sleep(0.8)

    # Intentar extraer el H1 real de la página (más fiable que page.title())
    title = ""
    h1_selectors = [
        "h1.category-header__name",
        "h1[data-test='category-title']",
        ".category-header h1",
        ".paper--white h1",
        "h1",
    ]
    for sel in h1_selectors:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                text = el.inner_text(timeout=3000).strip()
                if text and len(text) > 2:
                    title = text
                    break
        except Exception:
            continue

    # Fallback: título del tab del navegador
    if not title:
        try:
            title = page.title()
        except Exception:
            title = ""

    page_loaded = bool(title and len(title) > 2)

    return {
        "page_title":  title,
        "page_loaded": page_loaded,
    }


# ── RUN PRINCIPAL ─────────────────────────────────────────
def run():
    results   = []
    latencies = []

    started_at = datetime.now().isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ]
        )

        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        # Ocultar señales de automatización
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()

        # ── Paso 1: cargar estructura de categorías ──────
        flat_list = get_structure(page)

        if not flat_list:
            print("❌ No se encontraron categorías. Abortando.")
            browser.close()
            return

        total_available = len(flat_list)

        # Iterar solo las subcategorías únicas disponibles, máximo 100
        target = min(100, total_available)
        items_to_run = flat_list[:target]

        print(f"\n🚀 Iterando {target} subcategorías únicas (disponibles: {total_available})\n")

        # ── Paso 2: iteraciones sin repetición ───────────
        for i, item in enumerate(items_to_run):
            start = time.time()

            print(f"[{i + 1:>3}/{target}] {item['category']} › {item['subcategory']}")

            success = False
            attempt = 0

            # Retry con backoff exponencial (máx. 3 intentos)
            while attempt < 3 and not success:
                attempt += 1
                try:
                    if attempt > 1:
                        wait = 2.0 * (2 ** (attempt - 1)) + random.uniform(-0.5, 0.5)
                        print(f"   ↩  Reintento {attempt}/3 — esperando {wait:.1f}s")
                        time.sleep(wait)

                    data    = scrape_item(page, item)
                    elapsed = round(time.time() - start, 3)
                    latencies.append(elapsed)

                    results.append({
                        "iteration":    i + 1,
                        "category":     item["category"],
                        "subcategory":  item["subcategory"],
                        "url":          item["url"],
                        "page_title":   data["page_title"],
                        "page_loaded":  data["page_loaded"],
                        "status":       "success" if attempt == 1 else "retry_success",
                        "attempts":     attempt,
                        "latency_s":    elapsed,
                        "timestamp":    datetime.now().isoformat(),
                    })

                    print(f"   ✅ OK | {elapsed:.2f}s | '{data['page_title'][:60]}'")
                    success = True

                except PWTimeout:
                    print(f"   ⏱  Timeout (intento {attempt})")
                except Exception as e:
                    print(f"   ⚠  {type(e).__name__} (intento {attempt}): {e}")

            # Si falló tras 3 intentos, registrar como failed
            if not success:
                elapsed = round(time.time() - start, 3)
                results.append({
                    "iteration":    i + 1,
                    "category":     item["category"],
                    "subcategory":  item["subcategory"],
                    "url":          item["url"],
                    "page_title":   "",
                    "page_loaded":  False,
                    "status":       "failed",
                    "attempts":     attempt,
                    "latency_s":    elapsed,
                    "timestamp":    datetime.now().isoformat(),
                })
                print(f"   ❌ FAILED")
                # Pausa más larga tras fallo para evitar bloqueos
                time.sleep(random.uniform(4.0, 7.0))
            else:
                human_delay(1.5, 2.5)

            # Rotar User-Agent cada 25 iteraciones
            if (i + 1) % 25 == 0 and i < target - 1:
                new_ua = random.choice(USER_AGENTS)
                print(f"\n🔄 Rotando User-Agent → {new_ua[:40]}...\n")
                context.set_extra_http_headers({"User-Agent": new_ua})

        browser.close()

    finished_at = datetime.now().isoformat()

    # ── GUARDAR CSV ──────────────────────────────────────
    fieldnames = [
        "iteration", "category", "subcategory", "url",
        "page_title", "page_loaded",
        "status", "attempts", "latency_s", "timestamp",
    ]

    with open("g2_dataset.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # ── REPORTE DE RENDIMIENTO ───────────────────────────
    successes  = sum(1 for r in results if r["status"] != "failed")
    retries    = sum(1 for r in results if r["status"] == "retry_success")
    failures   = 100 - successes

    sorted_lat = sorted(latencies)
    p95_idx    = max(0, int(len(sorted_lat) * 0.95) - 1)

    report = {
        "started_at":            started_at,
        "finished_at":           finished_at,
        "total_iterations":      len(results),
        # Tasa de éxito
        "successes":             successes,
        "failures":              len(results) - successes,
        "success_rate_pct":      round(successes / len(results) * 100, 1) if results else 0,
        # Estabilidad
        "retry_recoveries":      retries,
        # Latencia
        "avg_latency_s":         round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "p95_latency_s":         round(sorted_lat[p95_idx], 3) if sorted_lat else 0,
        "min_latency_s":         round(min(latencies), 3) if latencies else 0,
        "max_latency_s":         round(max(latencies), 3) if latencies else 0,
        # Manejo de excepciones
        "exception_strategy":    "Backoff exponencial: 2s, 4s, 8s (+jitter). Pausa 4-7s tras fallo total.",
        "user_agent_rotation":   "Cada 25 iteraciones",
    }

    with open("performance_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ── CONSOLA: reporte visual ──────────────────────────
    bar = "═" * 52
    print(f"\n{bar}")
    print("   📊  REPORTE DE RENDIMIENTO — G2 SCRAPER")
    print(bar)
    total_ran = len(results)
    print(f"   Iteraciones      : {total_ran}")
    print(f"   ✅ Éxitos        : {successes}")
    print(f"   🔁 Recuperados   : {retries}")
    print(f"   ❌ Fallos        : {total_ran - successes}")
    print(f"   Tasa de éxito    : {report['success_rate_pct']}%")
    print(f"   Latencia prom.   : {report['avg_latency_s']}s")
    print(f"   Latencia P95     : {report['p95_latency_s']}s")
    print(f"   Latencia mín.    : {report['min_latency_s']}s")
    print(f"   Latencia máx.    : {report['max_latency_s']}s")
    print(bar)
    print(f"\n💾 Dataset  → g2_dataset.csv")
    print(f"📋 Reporte  → performance_report.json")


if __name__ == "__main__":
    print("🌐 G2 Scraper — Prueba Técnica Tusdatos.co")
    print("=" * 52)
    run()