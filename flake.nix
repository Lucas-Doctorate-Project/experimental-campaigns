{
  description = "Description for the project";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    batsim.url = "github:Lucas-Doctorate-Project/batsim";
    batsched.url = "github:Lucas-Doctorate-Project/batsched";
    evalys.url = "github:Lucas-Doctorate-Project/evalys";
  };

  outputs = inputs@{ flake-parts, batsim, batsched, evalys, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-darwin" ];
      perSystem = { config, self', inputs', pkgs, system, ... }:
        let
          batsim-pkg = inputs.batsim.packages.${system}.default;
          batsched-pkg = inputs.batsched.packages.${system}.default;
          evalys-pkg = inputs.evalys.packages.${system}.evalys;

          # Build the Python env from the interpreter evalys was built against,
          # so procset, pandas and matplotlib stay binary-compatible.
          python = evalys-pkg.pythonModule;
          pythonEnv = python.withPackages (ps: [
            ps.pandas
            ps.matplotlib
            evalys-pkg
          ]);
        in {
          devShells.default = pkgs.mkShell {
            packages = [
              pkgs.go
              batsim-pkg
              batsched-pkg
              pythonEnv
            ];
          };
        };
    };
}
