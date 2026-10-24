// Messages that come from the server (validation, readiness, errors) and from the API client.
const server: Record<string, string> = {
  // API client
  "Cannot reach the server. Check the network connection.": "No hay conexión con el servidor. Revisa el Wi-Fi o los datos móviles.",
  "The photo is too large to upload. Try again, or use a lower camera resolution.": "La foto es demasiado grande para subirla. Inténtalo de nuevo o usa una resolución de cámara más baja.",
  // Friendly headings (components/ui.tsx)
  "Before you can save this:": "Antes de guardar esto:",
  "A few checks are still missing. Tap one to go there:": "Todavía faltan algunas verificaciones. Toca una para ir a ella:",
  "No connection to the server. Check the Wi-Fi or mobile data and try again.": "No hay conexión con el servidor. Revisa el Wi-Fi o los datos móviles e inténtalo de nuevo.",
  // Saving a result
  "Take a photo first.": "Primero toma una foto.",
  "Tick “I checked this myself, in person” first.": "Primero marca “Lo revisé yo, en persona”.",
  "Your supervisor asked for a new photo. Take a new photo first.": "Tu supervisor pidió una foto nueva. Primero toma una foto nueva.",
  "Your supervisor asked you to check this again. Write in the notes what you checked.": "Tu supervisor te pidió revisar esto otra vez. Escribe en las notas qué revisaste.",
  "The AI suggested another photo. Take a new photo, or tap “Use it anyway” and explain why this photo is good enough.": "La IA sugirió otra foto. Toma una foto nueva, o toca “Usarla de todos modos” y explica por qué esta foto es suficiente.",
  "A problem is already reported for this check. Cancel it on the Problems page first if it was a mistake.": "Ya hay un problema reportado en esta verificación. Si fue un error, primero cancélalo en la página de Problemas.",
  "Take a photo of the problem first.": "Primero toma una foto del problema.",
  "Describe what is wrong.": "Describe qué está mal.",
  "Write in the notes why this check doesn't apply.": "Escribe en las notas por qué esta verificación no aplica.",
  // Readiness (sending for review)
  "Not done yet": "Todavía no se hace",
  "Photo taken; choose a result": "Foto tomada; elige un resultado",
  "A new photo is needed": "Se necesita una foto nueva",
  "Optional check not done": "Verificación opcional sin hacer",
  "Photo missing": "Falta la foto",
  "Problem reported without a description": "Problema reportado sin descripción",
  "Required check marked \"doesn't apply\" (the supervisor will see the reason)": "Verificación obligatoria marcada como “no aplica” (el supervisor verá el motivo)",
  "Marked as good although the AI suggested another photo (overridden, with a reason)": "Marcada como bien aunque la IA sugirió otra foto (se justificó el motivo)",
  "A critical problem must be fixed and closed before sending": "Un problema crítico debe corregirse y cerrarse antes de enviar",
  // Errors
  "Requirement cannot be dispositioned": "Antes de guardar esto:",
  "Inspection cannot be submitted yet": "Todavía faltan algunas verificaciones. Toca una para ir a ella:",
  "A comment is required to reject an inspection": "Escribe un comentario para rechazar la inspección",
  "A reason is required to void a finding": "Escribe el motivo para cancelar el problema",
  "An 'after' photo of the corrected condition is required to close the finding": "Para cerrar el problema se necesita una foto “después” que muestre la corrección",
  "An inspection of this unit is awaiting supervisor review. Wait for the decision first.": "Una inspección de esta unidad está esperando la revisión del supervisor. Primero espera su decisión.",
  "Describe the corrective action taken": "Describe qué se hizo para corregirlo",
  "Finding not found": "No se encontró el problema",
  "Finding is closed": "El problema ya está cerrado",
  "Inspection item not found": "No se encontró la verificación",
  "Inspection not found": "No se encontró la inspección",
  "Prepared demo photos can only be used in a demo inspection": "Las fotos de práctica solo se pueden usar en una inspección de práctica",
  "Select at least one requirement that needs additional evidence": "Marca al menos una verificación que necesite cambios",
  "The reviewer must be a different person from the inspector": "Quien revisa debe ser una persona distinta del inspector",
  "This demo photo belongs to a different requirement": "Esta foto de práctica es de otra verificación",
  "This product revision has no inspection requirements": "Este equipo no tiene verificaciones definidas",
  "Unknown inspection item in request": "Verificación desconocida en la solicitud",
  "Verification must be performed by someone other than the person who did the work": "La comprobación la debe hacer alguien distinto de quien hizo el trabajo",
  "assigned_to is required": "Escribe quién lo va a corregir",
  "Demo evidence not found": "No se encontró la foto de práctica",
  "Evidence file missing": "Falta el archivo de la foto",
  "Evidence not found": "No se encontró la foto",
  "Inspection evidence not found": "No se encontró la foto de la inspección",
  "Not found": "No encontrado",
  "Package not found": "No se encontró el paquete",
  "Product instance not found": "No se encontró la unidad",
  "Revision not found": "No se encontró la revisión de ingeniería",
  "Uploaded file is not a supported image (use JPEG or PNG)": "El archivo no es una imagen compatible (usa JPEG o PNG)",
  "actor is required": "Falta el nombre de quien hace la acción",
  "Package failed validation": "El paquete no pasó la validación",
};

const SEVERITY: Record<string, string> = { minor: "menor", moderate: "moderado", serious: "grave", critical: "crítico" };

// Server messages that carry values.
export const SERVER_PATTERNS: [RegExp, (...m: string[]) => string][] = [
  [/^Marked as good although the AI flagged something to check: (.*)$/s, (_, x) => `Marcada como bien aunque la IA señaló algo por revisar: ${x}`],
  [/^A (\w+) problem is open; it will go to the supervisor and be tracked until fixed$/, (_, s) => `Hay un problema ${SEVERITY[s] ?? s} abierto; irá al supervisor y se le dará seguimiento hasta corregirlo`],
  [/^A (live|demo) inspection of this unit is already open\. Finish it before starting a different mode\.$/, (_, m) => `Ya hay una inspección ${m === "demo" ? "de práctica" : "real"} abierta para esta unidad. Termínala antes de iniciar otro tipo.`],
  [/^Inspection is '(\w+)' and can no longer be edited by the inspector$/, () => "Esta inspección ya no la puede modificar el inspector"],
  [/^Only submitted inspections can be reviewed.*$/, () => "Solo se pueden revisar las inspecciones enviadas"],
  [/^Finding cannot move from '(\w+)' to '(\w+)'$/, () => "Ese cambio no es posible en el estado actual del problema"],
  [/^Image larger than (\d+) MB$/, (_, n) => `La imagen pesa más de ${n} MB`],
  [/^Unknown product instance (.*)$/, (_, s) => `Unidad desconocida ${s}`],
  [/^Inspection status is '(\w+)'$/, () => "La inspección ya no está abierta"],
  [/^Request failed \((\d+)\)$/, (_, n) => `La solicitud falló (${n})`],
];

export default server;
