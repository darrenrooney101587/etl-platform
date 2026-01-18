#!/bin/bash

set -e

if [ -z "$1" ]; then
  echo "Usage: ./release.sh <new-version> [release-comment]"
  echo "Example: ./release.sh 0.2.0 \"Fix bug X and add Y\""
  exit 1
fi

NEW_VERSION=$1
RELEASE_MSG=${2:-}
PYPROJECT="pyproject.toml"
SETUP_PY="setup.py"

echo "[INFO] Bumping version to $NEW_VERSION"

# macOS sed inline edit
sed -i '' "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"
sed -i '' "s/version=\".*\"/version=\"$NEW_VERSION\"/" "$SETUP_PY"

git add .

if [ -n "$RELEASE_MSG" ]; then
  git commit -m "Release version $NEW_VERSION: $RELEASE_MSG"
else
  git commit -m "Release version $NEW_VERSION"
fi

git tag -a "v$NEW_VERSION" -m "${RELEASE_MSG:-Release $NEW_VERSION}"

git push origin main
git push origin "v$NEW_VERSION"

echo "[DONE] Released version $NEW_VERSION"
