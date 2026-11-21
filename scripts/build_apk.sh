#!/usr/bin/env bash
set -e

# ==============================================================================
# Build Script for Algo Mobile Android APK
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
ANDROID_DIR="${FRONTEND_DIR}/android"

echo "=== Building Algo Mobile Web Assets ==="
cd "${FRONTEND_DIR}"
npm run build

echo "=== Syncing Capacitor Android Project ==="
npx cap sync android

echo "=== Checking Android Build Environment ==="
if ! command -v javac >/dev/null 2>&1 || ! java -version >/dev/null 2>&1; then
    echo "Notice: Java Development Kit (JDK 17+) is not configured in this shell environment."
    echo ""
    echo "Options to generate your .apk:"
    echo "1. GitHub Actions (Automated Cloud Build):"
    echo "   Push this branch (feature/mobile-client-app) to GitHub."
    echo "   The GitHub Actions workflow (.github/workflows/build-apk.yml) will build and provide"
    echo "   the downloadable AlgoMobile-debug.apk under the Actions tab."
    echo ""
    echo "2. Android Studio (Local GUI Build):"
    echo "   Open the Android project in Android Studio:"
    echo "     open -a 'Android Studio' '${ANDROID_DIR}'"
    echo "   Then select: Build > Build Bundle(s) / APK(s) > Build APK(s)."
    echo ""
    echo "3. Install OpenJDK locally:"
    echo "   brew install openjdk@17"
    echo "   sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk"
    echo "   export JAVA_HOME=/opt/homebrew/opt/openjdk@17"
    echo "   cd '${ANDROID_DIR}' && ./gradlew assembleDebug"
    exit 0
fi

echo "=== Running Gradle Build for Debug APK ==="
cd "${ANDROID_DIR}"
chmod +x gradlew
./gradlew assembleDebug

APK_PATH="${ANDROID_DIR}/app/build/outputs/apk/debug/app-debug.apk"
if [ -f "${APK_PATH}" ]; then
    echo "=== APK Build Successful! ==="
    echo "Generated APK location: ${APK_PATH}"
else
    echo "Gradle build completed, please check: ${ANDROID_DIR}/app/build/outputs/apk/"
fi
