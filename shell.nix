{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "fizzualizer-env";
  packages = with pkgs; [
    python3
    python3Packages.numpy
    python3Packages.pygame
    python3Packages.moderngl
    playerctl
  ];
  shellHook = ''
    echo "Fizzualizer ready — run: python fizzualizer.py"
  '';
}
