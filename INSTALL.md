# Instalar Dova Translator

El archivo `dist/DovaTranslator-1.0.0-win11-x64.msi` contiene la aplicación, Python y sus dependencias. No necesitas instalar Python ni ejecutar archivos BAT.

## Requisitos

- Windows 11 de 64 bits (x64).
- Micrófono para dictar.
- Conexión a Internet para descargar el modelo de voz local la primera vez, o para usar los modos OpenAI.

## Instalación

1. Abre el archivo MSI y pulsa **Instalar**.
2. Abre **Dova Translator** desde el menú Inicio o su acceso directo en el escritorio.
3. Elige el micrófono en **Ajustes**. Mantén `Ctrl + Alt + Espacio` mientras hablas y suelta las teclas para escribir.

La aplicación se instala para tu usuario en `%LOCALAPPDATA%\Programs\DovaTranslator`. Incluye su propio entorno de Python y no cambia el Python de otras aplicaciones.

La primera carga del modelo local puede tardar y descargar varios cientos de MB. Los modos OpenAI requieren que introduzcas tu propia clave API en la aplicación; el uso de ese servicio se factura por separado. El instalador no contiene claves, configuraciones ni grabaciones personales.

La corrección gramatical local con LanguageTool requiere Java; esa función es opcional.

## Datos y desinstalación

Los ajustes de esta edición se guardan en `%APPDATA%\DovaTranslator`; las claves API se guardan en el Administrador de credenciales de Windows. Es independiente de la carpeta de desarrollo `translator`.

Para desinstalar, abre **Configuración → Aplicaciones → Aplicaciones instaladas → Dova Translator → Desinstalar**. Los ajustes personales se conservan.

## Distribución

Este paquete inicial no tiene firma digital del editor. Las políticas de seguridad de cada organización pueden exigir un paquete firmado. Las licencias de los componentes de terceros acompañan a la aplicación.
