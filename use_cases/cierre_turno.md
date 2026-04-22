# Caso de Uso: Cierre de Turno Clínico

## Problema

Una clínica ambulatoria cierra el turno diario de forma manual: el personal recopila datos de pacientes, revisa el inventario físicamente, consulta alertas sanitarias y redacta el reporte a mano. El proceso toma 30-45 minutos, es propenso a omisiones y no deja trazabilidad estructurada.

## Solución

El agente recibe un único prompt en lenguaje natural y genera el reporte completo en segundos, consultando automáticamente todas las fuentes relevantes.

**Prompt de entrada:**
```
"Genera el cierre del turno de hoy para la clínica Centro Médico Norte"
```

---

## Flujo de ejecución

El agente decide autónomamente qué herramientas usar y en qué orden. El orden óptimo es:

```
1. get_epidemiological_alerts(country="colombia")
        ↓
2. get_shift_summary(date=hoy, clinic_name="Centro Médico Norte")
   get_top_diagnoses(date=hoy, limit=3)
        ↓
3. get_stock_status()
   compare_stock_consumption(date=hoy)
        ↓
4. calculate_occupancy(visits_today=N, max_capacity=15)
   project_stock(stock_items=[...])
   generate_recommendations(occupancy_data=..., stock_projections=[...])
        ↓
5. write_file(path="cierre_2026-04-21.md", content=<reporte>)
```

Cada paso alimenta al siguiente: los conteos del paso 2 entran al paso 4, y los datos de inventario del paso 3 entran a `project_stock`.

---

## Ejemplo de reporte generado

```markdown
# Cierre de Turno — Centro Médico Norte
**Fecha:** 2026-04-21 | **Hora de generación:** 17:32

## 1. Resumen del Turno
- **Pacientes atendidos:** 8
- **Inicio del turno:** 08:00 | **Cierre:** 16:45
- **Médicos en turno:** Dr. Castro, Dr. Ramírez

## 2. Top 3 Diagnósticos del Día
| # | Código CIE | Diagnóstico | Casos |
|---|-----------|-------------|-------|
| 1 | J06.9 | Infección respiratoria aguda alta | 3 |
| 2 | I10   | Hipertensión esencial             | 2 |
| 3 | E11   | Diabetes mellitus tipo 2          | 1 |

## 3. Estado del Inventario
| Medicamento | Unidad | Stock actual | Umbral mínimo | Estado |
|-------------|--------|-------------|---------------|--------|
| Amoxicilina | cáp. 500mg | 4 | 15 | 🚨 crítico |
| Lorazepam   | tab. 1mg   | 2 |  5 | 🚨 crítico |
| Lisinopril  | tab. 10mg  | 8 | 10 | ⚠️ bajo    |
| Paracetamol | tab. 500mg | 120 | 25 | ✅ normal |

## 4. Proyección para Mañana
| Medicamento | Stock hoy | Consumido hoy | Stock mañana | Días restantes | Reorden |
|-------------|-----------|---------------|-------------|----------------|---------|
| Amoxicilina | 4 | 3 | 1 | 1 | 🔴 urgente |
| Lorazepam   | 2 | 1 | 1 | 2 | 🔴 urgente |
| Lisinopril  | 8 | 2 | 6 | 3 | 🟡 alta    |

## 5. Alertas Sanitarias
**Nivel:** normal
- Situación epidemiológica estable en Colombia. Continuar protocolos estándar.

## 6. Recomendaciones
- Reordenar HOY: Amoxicilina (1 día restante) y Lorazepam (2 días restantes).
- Gestionar reposición pronto: Lisinopril (3 días).
- Ocupación del turno: 53% (8/15 pacientes). Capacidad disponible para turno adicional.
- Revisar agendamiento para aumentar captación de pacientes crónicos.

---
*Reporte generado automáticamente · 2026-04-21*
```

---

## Manejo de errores

| Escenario | Comportamiento del agente |
|---|---|
| API disease.sh no responde (timeout) | Continúa el flujo. La sección "Alertas Sanitarias" indica: *"No fue posible verificar estado epidemiológico (timeout)."* |
| Sin pacientes registrados hoy | El reporte indica: *"Sin pacientes registrados. Verificar carga del turno."* El resto del flujo continúa. |
| Stock en cero para algún medicamento | La sección de inventario marca ⚠️ ACCIÓN URGENTE con detalle del medicamento afectado. |
| Fallo al escribir el archivo | El agente reporta el error con ruta y detalle para que el operador pueda actuar manualmente. |

---

## Cómo extender el caso

**Agregar una nueva clínica:** el agente extrae el nombre desde el prompt. No requiere cambios en código — solo que existan visitas en la BD con ese `clinic_name`.

**Cambiar la capacidad máxima:** modificar `max_capacity=15` en el system prompt (`agent/prompts.py`) o pasarlo como parte del prompt del operador.

**Agregar un nuevo MCP:** crear el servidor en `mcp_servers/<nombre>/server.py`, registrarlo en `_MCP_MODULES` dentro de `agent/main.py` y describir la herramienta nueva en el system prompt.

**Programar el cierre automático:** ejecutar el agente vía cron o task scheduler:
```bash
# Linux/Mac
0 17 * * 1-5 cd /path/to/cun_test && uv run cun-agent "Genera el cierre del turno de hoy para la clínica Centro Médico Norte"

# Windows Task Scheduler
uv run cun-agent "Genera el cierre del turno de hoy para la clínica Centro Médico Norte"
```
