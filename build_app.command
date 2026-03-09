#!/bin/bash
# SampleForge — Build standalone .app para macOS
# Doble click para compilar. El resultado queda en dist/SampleForge.app
# NOTA: el build tarda 5-15 minutos y el .app resultante pesa ~3-4 GB.

cd "$(dirname "$0")"
clear

echo ""
echo "  =========================================="
echo "   SampleForge — Build .app para macOS"
echo "  =========================================="
echo ""

# --- Verificar que el venv existe ---
if [ ! -f ".venv/bin/activate" ]; then
    echo "  [ERROR] Primero ejecuta SampleForge.command para instalar dependencias."
    echo ""
    read -p "  Presiona Enter para cerrar..."
    exit 1
fi

source .venv/bin/activate

# --- Instalar PyInstaller si no está ---
python -c "import PyInstaller" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "  Instalando PyInstaller..."
    pip install pyinstaller --quiet
    echo "  OK"
    echo ""
fi

# --- Limpiar builds anteriores ---
echo "  Limpiando builds anteriores..."
rm -rf build dist __pycache__
echo "  OK"
echo ""

# --- Build ---
echo "  Compilando SampleForge.app..."
echo "  (esto puede tardar 5-15 minutos)"
echo ""

pyinstaller SampleForge.spec \
    --noconfirm \
    --clean \
    --log-level WARN

BUILD_RESULT=$?

if [ $BUILD_RESULT -ne 0 ]; then
    echo ""
    echo "  [ERROR] El build falló."
    echo "  Revisa los mensajes de arriba."
    echo ""
    read -p "  Presiona Enter para cerrar..."
    exit 1
fi

# --- Verificar que se generó el .app ---
if [ ! -d "dist/SampleForge.app" ]; then
    echo "  [ERROR] No se encontró dist/SampleForge.app"
    read -p "  Presiona Enter para cerrar..."
    exit 1
fi

APP_SIZE=$(du -sh "dist/SampleForge.app" | cut -f1)

echo ""
echo "  =========================================="
echo "   Build completado!"
echo "  =========================================="
echo ""
echo "  Ubicacion: $(pwd)/dist/SampleForge.app"
echo "  Tamaño:    $APP_SIZE"
echo ""
echo "  IMPORTANTE:"
echo "  - El modelo CLAP (~1.5 GB) se descarga la"
echo "    primera vez que se abre la app."
echo "  - Para compartir, comprime dist/SampleForge.app"
echo "    con click derecho → Comprimir."
echo "  - En otra Mac: descomprimir, luego"
echo "    click derecho → Abrir (primera vez)"
echo "    para saltear Gatekeeper."
echo ""

# --- Ofrecer crear DMG ---
read -p "  Crear .dmg para distribucion? (s/n): " CREATE_DMG
if [[ "$CREATE_DMG" =~ ^[sS]$ ]]; then
    echo ""
    echo "  Creando SampleForge.dmg..."
    hdiutil create \
        -volname "SampleForge" \
        -srcfolder "dist/SampleForge.app" \
        -ov \
        -format UDZO \
        "dist/SampleForge.dmg"

    if [ $? -eq 0 ]; then
        DMG_SIZE=$(du -sh "dist/SampleForge.dmg" | cut -f1)
        echo "  SampleForge.dmg creado ($DMG_SIZE)"
        echo "  Listo para compartir!"
    else
        echo "  [WARN] No se pudo crear el DMG (el .app sigue disponible)."
    fi
fi

echo ""
read -p "  Presiona Enter para cerrar..."
