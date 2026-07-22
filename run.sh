#!/usr/bin/env bash
# Fizzualizer launcher
cd "$(dirname "$0")"
exec nix-shell shell.nix --command "python fizzualizer.py"
