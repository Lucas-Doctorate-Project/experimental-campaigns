{
  description = "Description for the project";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    batsim.url = "github:Lucas-Doctorate-Project/batsim";
    batsched.url = "github:Lucas-Doctorate-Project/batsched";
  };

  outputs = inputs@{ flake-parts, batsim, batsched, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-darwin" ];
      perSystem = { config, self', inputs', pkgs, system, ... }:
        let
          batsim-pkg = inputs.batsim.packages.${system}.default;
          batsched-pkg = inputs.batsched.packages.${system}.default;
        in {
          devShells.default = pkgs.mkShell {
            packages = with pkgs; [
              go
              batsim-pkg
              batsched-pkg
            ];
          };
        };
    };
}
