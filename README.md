# G2.com Scraper — Prueba Técnica Tusdatos.co

Motor de extracción resiliente para G2.com que procesa **100 solicitudes** manteniendo alta tasa de éxito y datos íntegros.

---

## Estructura del repositorio

```
g2-scraper/
├── g2_scraper.py            # Script principal
├── g2_dataset.csv           # Dataset normalizado (100 muestras)
├── performance_report.json  # Reporte de métricas
└── README.md
```

---

## Requisitos

```bash
pip install playwright
playwright install chromium
```

`requirements.txt`:
```
playwright>=1.43.0
```

---

## Uso

```bash
python g2_scraper.py
```

Al finalizar genera:
- `g2_dataset.csv` — 100 registros normalizados
- `performance_report.json` — métricas de rendimiento

---

## Campos del dataset

| Campo | Descripción |
|---|---|
| `iteration` | Número de iteración (1–100) |
| `category` | Categoría principal de G2 |
| `subcategory` | Subcategoría dentro de la categoría |
| `url` | URL de la subcategoría en G2.com |
| `page_title` | Título HTML de la página visitada |
| `page_loaded` | Booleano — confirmación de carga exitosa |
| `status` | `success`, `retry_success` o `failed` |
| `attempts` | Número de intentos realizados |
| `latency_s` | Latencia en segundos |
| `timestamp` | Fecha y hora de la extracción |

---

## Métricas del reporte

- **Tasa de éxito** — porcentaje de capturas limpias vs. errores
- **Recuperaciones por retry** — iteraciones rescatadas con backoff
- **Latencia promedio, P95, mín. y máx.**
- **Estrategia de excepciones** — backoff exponencial + rotación de User-Agent

---

## Arquitectura

Ver `ARQUITECTURA.docx` para la explicación técnica completa de la estrategia de resiliencia.

---

## Autor

Prueba técnica — Tusdatos.co
