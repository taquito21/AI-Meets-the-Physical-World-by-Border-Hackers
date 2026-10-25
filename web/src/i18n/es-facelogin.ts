// Face login: the sign-in button, the "My face" page and the server's face-login messages.
const faceLogin: Record<string, string> = {
  "Sign in with my face": "Entrar con mi rostro",
  "or": "o",
  "To use your face, first sign in with your password and register it in “My face”.": "Para usar tu rostro, primero entra con tu contraseña y regístralo en “Mi rostro”.",
  "We didn't recognize your face. Try again with more light, or sign in with your password.": "No reconocimos tu rostro. Inténtalo con más luz, o entra con tu contraseña.",
  "Preparing the camera…": "Preparando la cámara…",
  "My face": "Mi rostro",
  "Sign in by looking at the camera instead of typing your password.": "Entra mirando a la cámara en lugar de escribir tu contraseña.",
  "Your face is registered. Next time, choose “Sign in with my face”.": "Tu rostro está registrado. La próxima vez elige “Entrar con mi rostro”.",
  "Delete my face data": "Borrar mis datos de rostro",
  "Delete your face data? You can register it again later.": "¿Borrar tus datos de rostro? Puedes registrarlo de nuevo después.",
  "We save only 128 numbers calculated from your face, never a photo.": "Solo guardamos 128 números calculados a partir de tu rostro, nunca una foto.",
  "They are used only to sign you in to this app, and you can delete them at any time.": "Solo se usan para que entres a esta app, y puedes borrarlos cuando quieras.",
  "It does not detect printed photos, so your password always keeps working.": "No detecta fotos impresas, por eso tu contraseña siempre sigue funcionando.",
  "I agree to register my face to sign in.": "Acepto registrar mi rostro para entrar.",
  "Register my face": "Registrar mi rostro",
  "Saving…": "Guardando…",
  // Server messages
  "Face not recognized": "No reconocimos tu rostro. Inténtalo con más luz, o entra con tu contraseña.",
  "Face data incomplete. Try again.": "Faltaron datos del rostro. Inténtalo de nuevo.",
  "Consent is required to save your face.": "Necesitamos tu consentimiento para guardar tu rostro.",
  "The samples don't look like the same face. Try again with good light.": "Las muestras no parecen del mismo rostro. Inténtalo de nuevo con buena luz.",
  "This face is already registered to another account.": "Este rostro ya está registrado en otra cuenta.",
  "Face login is not set up yet: apply backend/supabase/schema.sql in Supabase.": "El inicio con rostro todavía no está configurado en el servidor.",
  "Face login needs the Supabase login to be configured": "El inicio con rostro necesita que el inicio de sesión de Supabase esté configurado.",
  "Could not start the session. Log in with your password.": "No se pudo iniciar la sesión. Entra con tu contraseña.",
};

export default faceLogin;
