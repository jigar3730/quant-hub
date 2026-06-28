#!/usr/bin/env bash
# One-shot helper: verify GitHub SSH, then push main.
set -euo pipefail
cd "$(dirname "$0")/.."

PUB_KEY_FILE="${HOME}/.ssh/id_ed25519.pub"
ADD_KEY_URL="https://github.com/settings/ssh/new"
REPO_URL="https://github.com/new?name=quant-hub"

echo "=== Quant Hub → GitHub push helper ==="
echo ""

if [[ ! -f "${PUB_KEY_FILE}" ]]; then
  echo "Generating SSH key..."
  ssh-keygen -t ed25519 -C "$(git config user.email)" -f "${HOME}/.ssh/id_ed25519" -N "" -q
fi

if ! grep -q 'Host github.com' "${HOME}/.ssh/config" 2>/dev/null; then
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  cat >> "${HOME}/.ssh/config" <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF
  chmod 600 "${HOME}/.ssh/config"
fi

echo "Local commits ready to push:"
git log origin/main..HEAD --oneline 2>/dev/null || git log -3 --oneline
echo ""

if ssh -T git@github.com -o BatchMode=yes 2>&1 | grep -qi 'successfully authenticated'; then
  echo "GitHub SSH: OK"
else
  echo "GitHub SSH: not authorized yet."
  echo ""
  echo "ONE-TIME SETUP (about 60 seconds):"
  echo "  1. Open: ${ADD_KEY_URL}"
  echo "  2. Title: quant-hub-server"
  echo "  3. Key type: Authentication Key"
  echo "  4. Paste this public key:"
  echo ""
  cat "${PUB_KEY_FILE}"
  echo ""
  echo "If repo does not exist yet, create it: ${REPO_URL}"
  echo "  (leave README/license unchecked — code already exists locally)"
  echo ""
  read -r -p "Press Enter after adding the key on GitHub..."
fi

echo "Pushing to origin main..."
git push -u origin main
echo "Done. Remote: $(git remote get-url origin)"
