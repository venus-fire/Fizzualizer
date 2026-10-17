#!/usr/bin/env bash
# Fizzualizer launcher
#
# Runs from a local .venv, creating it on first run.
# shell.nix is still there for Nix users: nix-shell shell.nix --command "python fizzualizer.py"
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found — creating it"
  UV="$(command -v uv || true)"
  if [ -z "$UV" ] && [ -x "$HOME/.hermes/bin/uv" ]; then UV="$HOME/.hermes/bin/uv"; fi
  if [ -n "$UV" ]; then
    "$UV" venv --python 3.13 .venv
    "$UV" pip install --python .venv/bin/python numpy pygame moderngl
  else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install numpy pygame moderngl
  fi
fi

exec .venv/bin/python fizzualizer.py "$@"
