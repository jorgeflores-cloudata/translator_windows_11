# Dova Translator para Windows 11

Dictado y traducción por voz para Windows. Haz clic en un campo de texto, mantén el atajo, habla y suelta: el texto aparece donde está el cursor. Incluye reconocimiento local con Whisper y modos opcionales de OpenAI.

## Instalador recomendado

Usa `dist/DovaTranslator-1.0.0-win11-x64.msi`. Es un único archivo con el intérprete de Python y las dependencias incluidos, icono propio, accesos directos y desinstalación desde Windows.

Consulta [INSTALL.md](INSTALL.md) para instalar y usar el paquete. Esta carpeta es independiente de `C:\VSCODE\translator`.

## Ejecutar el código fuente
Requiere **Python 3.12 de 64 bits**. Si usas el gestor oficial de Python, instálalo con `pymanager install 3.12`.

1. Primera vez: ejecuta `setup.bat` (crea el entorno en `%LOCALAPPDATA%\DovaTranslator\dev-venv-py312`, fuera de OneDrive).
2. Abre la app con `run.bat`. La primera vez descarga el modelo (~500 MB para `small`).
3. Haz clic en el campo donde quieres escribir, **mantén el atajo** (por defecto `Ctrl + Alt + Espacio`), habla y suelta.

El instalador usa paquetes precompilados y verifica las dependencias. Si falla, muestra un error y `run.bat` no inicia una instalación incompleta.

El panel **Señal del micrófono** muestra un ecualizador en vivo y avisa si el volumen es demasiado alto. Con **Micrófono siempre listo** activado, también se mueve entre dictados; si lo desactivas, muestra señal mientras grabas o pruebas el micrófono.

En el modo OpenAI en tiempo real, una respuesta vacía o incompleta se reintenta con la grabación por la vía normal de OpenAI. El volumen se limita antes de recortar los picos para evitar distorsión.

La traducción en tiempo real envía el audio mientras dictas y pide una respuesta de solo texto al soltar el atajo, para evitar la espera de generar audio traducido. La latencia puede variar según la conexión y el servicio.

## Modos
- Hablo español → escribe en inglés (Whisper traduce directamente)
- Hablo español → escribe en español
- Hablo inglés → escribe en inglés

## Corrección gramatical (modo inglés → inglés)
En **Ajustes → Gramática (EN→EN)**:
- **Sin corrección**: escribe lo que Whisper oyó.
- **LanguageTool (local)**: corrige en tu PC, el texto no sale del equipo. Requiere Java instalado; la primera vez descarga ~250 MB.
- **Claude API**: mejor calidad. El texto (no el audio) se envía a Anthropic. Requiere la variable de entorno `ANTHROPIC_API_KEY`. No dictes datos sensibles o de pacientes con esta opción.
- **OpenAI API**: igual que Claude, pero el texto se envía a OpenAI. Requiere `OPENAI_API_KEY`; el modelo se cambia con `OPENAI_MODEL` (por defecto `gpt-4.1-mini`). Misma advertencia sobre datos sensibles.

Si la corrección falla, se escribe el texto original y se avisa en el historial.

## Notas
- Si la app destino corre como administrador, ejecuta Translator también como administrador.
- Los ajustes se guardan en `%APPDATA%\DovaTranslator\settings.json`.
- Whisper solo traduce **a inglés**.
- Algunos antivirus marcan librerías de teclado global (`keyboard`); avisa a IT si hace falta.
