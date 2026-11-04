#!/usr/bin/env sh
# Build eSMAF on macOS or Linux. A thin wrapper around build.py.
#
#   ./build.sh              build
#   ./build.sh --notest     skip the scientific tests
#   ./build.sh --clean      start from a fresh build environment
cd "$(dirname "$0")" || exit 1

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        exec "$candidate" build.py "$@"
    fi
done

echo "Python 3.10 or newer was not found on this computer."
exit 1
