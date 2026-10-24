// Messages that come from the server (validation, access, errors) and from the API client and login.
const server: Record<string, string> = {
  // API client and login
  "Cannot reach the server. Check the network connection.": "No hay conexión con el servidor. Revisa el Wi-Fi o los datos móviles.",
  "The file is too large to upload.": "El archivo es demasiado grande para subirlo.",
  "Wrong email or password.": "Correo o contraseña incorrectos.",
  "Login is not configured on the server (SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY).": "El inicio de sesión no está configurado en el servidor.",
  // Login and access (backend/app/auth.py)
  "Log in first": "Primero inicia sesión",
  "Your session has expired. Log in again.": "Tu sesión expiró. Vuelve a iniciar sesión.",
  "This login has no profile yet. Ask your employer to add you.": "Esta cuenta todavía no tiene perfil. Pídele a tu jefe que te agregue.",
  "Only the employer can do this": "Solo el empleador puede hacer esto",
  "Could not load the login signing keys": "No se pudieron cargar las llaves del inicio de sesión",
  "Login is not configured (SUPABASE_URL is missing)": "El inicio de sesión no está configurado",
  // Jobs, tasks, evidence (backend/app/workflow.py)
  "Job not found": "No se encontró el trabajo",
  "Task not found": "No se encontró la tarea",
  "Media not found": "No se encontró el archivo",
  "A job needs a title": "El trabajo necesita un título",
  "Assign the job to an employee of your company": "Asigna el trabajo a un empleado de tu empresa",
  "Add at least one task": "Agrega al menos una tarea",
  "A linked media item does not exist in your company": "Uno de los archivos enlazados no existe en tu empresa",
  "Every task needs a description": "Cada tarea necesita una descripción",
  "Status must be one of pending, passed, failed, flagged": "Ese resultado no es válido",
  "Add a photo, a note, or both": "Agrega una foto, una nota o las dos",
  "Only the employee doing the job can add photos. Write a note instead.": "Solo el empleado que hace el trabajo puede agregar fotos. Escribe una nota.",
  "Evidence photo missing": "Falta la foto",
  "Photo evidence not found": "No se encontró la foto",
  "Uploaded file is not a supported image (use JPEG or PNG)": "El archivo no es una imagen compatible (usa JPEG o PNG)",
  "This record already exists or was just changed. Reload and try again.": "Esto ya existe o alguien lo acaba de cambiar. Recarga e inténtalo de nuevo.",
  // Media and document search (backend/app/media.py, rag.py)
  "This is not a valid .glb (binary glTF 2.0) file": "Este no es un archivo .glb válido",
  "Only documents (.pdf, .txt) can be made searchable": "Solo los documentos (.pdf, .txt) se pueden hacer consultables",
  "The document file is missing from storage": "Falta el archivo del documento",
  "Document search is not configured (set VOYAGE_API_KEY in backend/.env).": "La búsqueda en documentos no está configurada.",
  "Document search is busy right now. Try again in a minute.": "La búsqueda en documentos está ocupada. Inténtalo de nuevo en un minuto.",
  "Could not reach the embedding service (network).": "No se pudo conectar con el servicio de búsqueda (red).",
  "No text found in this file. Scanned PDFs (images of pages) cannot be searched yet.":
    "No se encontró texto en este archivo. Los PDF escaneados (fotos de páginas) todavía no se pueden consultar.",
  "Could not reach the AI provider (network).": "No se pudo conectar con la IA (red).",
  "The AI model declined to answer this question.": "La IA no quiso responder esta pregunta.",
};

export const SERVER_PATTERNS: [RegExp, (...m: string[]) => string][] = [
  [/^Too many attempts\. Try again in (\d+) seconds\.$/, (_, n) => `Demasiados intentos. Inténtalo de nuevo en ${n} segundos.`],
  [/^(Image|File) larger than (\d+) MB$/, (_, k, n) => `${k === "Image" ? "La imagen" : "El archivo"} pesa más de ${n} MB`],
  [/^Unsupported file type '(.*)'\..*$/, (_, x) => `Tipo de archivo no compatible (${x}). Usa .glb, .pdf, .txt, .jpg, .png o .webp`],
  [/^Could not read the PDF: (.*)$/s, () => "No se pudo leer el PDF"],
  [/^Request failed \((\d+)\)$/, (_, n) => `La solicitud falló (${n})`],
];

export default server;
