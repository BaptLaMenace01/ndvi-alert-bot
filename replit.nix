{ pkgs }: {
  deps = [
    pkgs.python311Full
    pkgs.python311Packages.pip
    pkgs.python311Packages.requests
    pkgs.python311Packages.python-dotenv
    pkgs.python311Packages.matplotlib
  ];
}
