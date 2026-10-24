// Shared vocabulary: menu, statuses, badges and industries. Other areas reuse these words so the app speaks one way.
const common: Record<string, string> = {
  // App shell
  "Field Assistant": "Asistente de Campo",
  "Equipment": "Equipos",
  "Review": "Revisión",
  "Problems": "Problemas",
  "Dashboard": "Panel",
  "Language": "Idioma",
  "Temporary test deployment: data is not permanent and may reset at any time.": "Versión de prueba temporal: los datos no son permanentes y pueden borrarse en cualquier momento.",
  "Page not found": "Página no encontrada",
  "Go to the start": "Ir al inicio",
  "Loading…": "Cargando…",
  "Change on the home screen": "Se cambia en la pantalla de inicio",
  "inspector": "inspector",
  "supervisor": "supervisor",
  "Evidence": "Foto",
  // Check (item) statuses
  "To do": "Por hacer",
  "Choose a result": "Elige un resultado",
  "New photo needed": "Falta foto nueva",
  "Looks good": "Está bien",
  "Problem reported": "Problema reportado",
  "Doesn't apply": "No aplica",
  // Part (component) statuses
  "Not checked yet": "Sin revisar",
  "Partly done": "Avance parcial",
  "Needs attention": "Requiere atención",
  "Done": "Revisado",
  // Severity
  "Minor": "Menor",
  "Moderate": "Moderado",
  "Serious": "Grave",
  "Critical: stop using it": "Crítico: dejar de usar",
  // Inspection statuses
  "In progress": "En proceso",
  "Sent for review": "Enviada a revisión",
  "Changes requested": "Se pidieron cambios",
  "Approved": "Aprobada",
  "Rejected": "Rechazada",
  // Badges
  "Real inspection": "Inspección real",
  "Practice": "Práctica",
  "Uses photos prepared in advance": "Usa fotos preparadas con anticipación",
  // Industries (from the equipment packages)
  "Furniture": "Mobiliario",
  "Electrical": "Eléctrico",
  "Facility Safety": "Seguridad de instalaciones",
  "General": "General",
  "All industries": "Todas",
  "Industry": "Industria",
  // Progress bar
  "{done} of {total} required checks done": "{done} de {total} verificaciones obligatorias hechas",
};

export default common;
